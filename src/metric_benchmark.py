"""Compare pixel and metric interpolation on the same calibrated subset of saved gaps."""

import argparse
import copy
from pathlib import Path

import numpy as np

from .benchmark import aggregate, build_manifest, evaluate, load_series, validate_saved_masks
from .common import read_csv, read_json, sha256_file, write_csv, write_json
from .georeference import GroundCalibration, project_path, settings


def calibrated_cases(pixel_series, base_manifest, projected_rows):
    """Keep a gap only if all its visible AND held-out positions have valid projections.

    Preserve indices and the global hidden mask; filtering never fills a missing
    projection or turns an excluded hidden sample into a visible support point.
    """
    metric_series = {}
    validity = {}
    for key, item in pixel_series.items():
        values = np.full_like(item["positions"], np.nan, dtype=float)
        valid = np.zeros(len(values), dtype=bool)
        for i, frame in enumerate(item["frames"]):
            row = projected_rows.get((item["video_id"], str(item["track_id"]), int(frame)))
            if row is not None and str(row["projection_valid"]).lower() == "true":
                value = np.array([float(row["east_m"]), float(row["north_m"])])
                if np.isfinite(value).all():
                    values[i], valid[i] = value, True
        metric_key = key.replace("object_pixels/", "object_ground/", 1)
        metric_series[metric_key] = {**item, "kind": "object_ground", "unit": "m", "positions": values}
        validity[key] = valid
    pixel_masks, metric_masks, excluded = [], [], []
    for mask in base_manifest["masks"]:
        indices = mask["visible_indices"] + mask["hidden_indices"]
        if not validity[mask["series_id"]][indices].all():
            excluded.append({"mask_id": mask["mask_id"], "reason": "support_or_reference_outside_valid_calibration"})
            continue
        pixel_masks.append(copy.deepcopy(mask))
        metric_masks.append({**copy.deepcopy(mask),
                             "series_id": mask["series_id"].replace("object_pixels/", "object_ground/", 1),
                             "mask_id": mask["mask_id"].replace("object_pixels/", "object_ground/", 1),
                             "source_mask_id": mask["mask_id"]})
    return metric_series, pixel_masks, metric_masks, excluded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data/urbantracker"))
    parser.add_argument("--config", type=Path, default=Path("configs/course_static.json"))
    parser.add_argument("--georeferencing", default="configs/georeferencing.json")
    parser.add_argument("--mask-file", type=Path, default=Path("data/urbantracker/masks/full_video.json"))
    parser.add_argument("--output", type=Path, default=Path("data/urbantracker/results/ground"))
    args = parser.parse_args()
    config = read_json(args.config)
    geometry_config = settings(args.georeferencing)
    pixel_series, sources, _ = load_series(args.data_root, config)
    base = validate_saved_masks(read_json(args.mask_file), build_manifest(pixel_series, config, sources))
    root = project_path(args.data_root)
    projected_rows, models, calibration_sources = {}, {}, {}
    for video in geometry_config["scenes"]:
        metadata = read_json(root / "prepared" / video / "metadata.json")
        model = GroundCalibration(geometry_config, video, metadata["width"], metadata["height"])
        models[video] = model
        projected_path = root / "georeferenced" / video / "tracks_ground.csv"
        provenance = read_json(projected_path.with_name("projection.json"))
        checks = {
            "calibration_sha256": sha256_file(model.path),
            "source_tracks_sha256": sha256_file(root / "tracks" / video / "tracks.csv"),
            "source_frames_sha256": sha256_file(root / "prepared" / video / "frames.csv"),
            "output_tracks_sha256": sha256_file(projected_path),
        }
        if any(provenance.get(field) != digest for field, digest in checks.items()):
            raise ValueError(f"Projection data are stale for {video}; run python3 -m src.project_ground")
        calibration_sources[str(model.path)] = checks["calibration_sha256"]
        calibration_sources[str(projected_path)] = checks["output_tracks_sha256"]
        for row in read_csv(projected_path):
            projected_rows[(video, row["track_id"], int(row["frame"]))] = row
    ground, paired, masks, excluded = calibrated_cases(pixel_series, base, projected_rows)
    if not masks:
        raise ValueError("No complete gap lies in the calibrated zone; inspect coverage or add ground control points")
    manifest = {"schema_version": 1, "config": config, "source_sha256": {**sources, **calibration_sources},
                "original_mask_sha256": sha256_file(args.mask_file), "masks": masks,
                "axis_order": ["east_m", "north_m"],
                "policy": "same hidden cases and supports as paired pixel baseline; filter validity only"}
    write_json(args.output / "metric_masks.json", manifest)
    write_csv(args.output / "excluded_masks.csv", excluded, ["mask_id", "reason"])
    metric_rows, predictions = evaluate(ground, manifest, config["methods"])
    pixel_rows, pixel_predictions = evaluate(pixel_series, {**base, "masks": paired}, config["methods"])
    geo_predictions = []
    for row in predictions:
        model = models[row["video_id"]]
        world = model.world_coordinates([[row["predicted_x"], row["predicted_y"]]])[0]
        geo_predictions.append({**row, "predicted_latitude_deg": float(world[0]), "predicted_longitude_deg": float(world[1])})
    write_csv(args.output / "metrics.csv", metric_rows + pixel_rows)
    write_csv(args.output / "predictions_ground.csv", geo_predictions)
    write_csv(args.output / "predictions_pixels_paired.csv", pixel_predictions)
    summary = aggregate(metric_rows + pixel_rows)
    write_csv(args.output / "summary.csv", summary)
    run = {
        "base_gap_count": len(base["masks"]), "valid_gap_count": len(masks), "excluded_gap_count": len(excluded),
        "methods": config["methods"], "calibration_sha256": calibration_sources,
        "reference": "YOLO/ByteTrack observations projected through the same calibration; not independent GPS ground truth",
        "kinematics": "evaluated by src.kinematic_benchmark against finite-difference estimates on complete projected tracks",
        "projection_order": "transform observed coordinates to metres, then interpolate in metres",
    }
    write_json(args.output / "run.json", run)
    lines = ["# Confronto sul piano stradale calibrato", "",
             f"Gap validi: {len(masks)} / {len(base['masks'])}; esclusi: {len(excluded)}.",
             "Le righe pixel e metri si riferiscono agli stessi gap e agli stessi supporti.",
             "Il riferimento metrico è la proiezione delle osservazioni YOLO/ByteTrack: non è un GPS indipendente.",
             "La cinematica è valutata separatamente con src.kinematic_benchmark; il riferimento è una stima a differenze finite, non una ground truth indipendente.", "",
             "| Spazio | Metodo | Gap | ADE | RMS | Unità | Fallimenti |", "|---|---|---:|---:|---:|---|---:|"]
    for row in summary:
        ade = f"{row['micro_ade']:.5f}" if row["micro_ade"] != "" else "n/a"
        rms = f"{row['micro_rms_position']:.5f}" if row["micro_rms_position"] != "" else "n/a"
        lines.append(f"| {row['kind']} | {row['method']} | {row['gap_size']} | {ade} | {rms} | {row['unit']} | {row['failed_masks']} |")
    (args.output / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print(f"Metric benchmark complete: {len(masks)} valid gaps; {args.output}")


if __name__ == "__main__":
    main()
