"""Evaluate velocity, acceleration, and heading from metric interpolants."""

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np

from .benchmark import build_manifest, load_series, validate_saved_masks
from .common import read_csv, read_json, sha256_file, write_csv, write_json
from .georeference import project_path, settings
from .interpolation import Interpolator
from .metric_benchmark import calibrated_cases


METHOD_LABELS = {
    "s1": "S1 linear",
    "s2": "S2 (extension)",
    "s3_natural": "Natural S3",
    "s3_clamped": "Clamped S3",
    "vandermonde": "Vandermonde",
    "lagrange": "Lagrange",
    "newton": "Newton",
    "rational_fh": "Floater–Hormann (extension)",
}


def circular_error(predicted, reference):
    return np.abs((predicted - reference + 180.0) % 360.0 - 180.0)


def reference_kinematics(times, positions):
    valid = np.isfinite(positions).all(axis=1)
    velocity = np.full_like(positions, np.nan)
    acceleration = np.full_like(positions, np.nan)
    starts = np.flatnonzero(valid & ~np.r_[False, valid[:-1]])
    ends = np.flatnonzero(valid & ~np.r_[valid[1:], False])
    for start, end in zip(starts, ends):
        if end - start + 1 < 3:
            continue
        segment_velocity = np.gradient(
            positions[start:end + 1], times[start:end + 1], axis=0, edge_order=2
        )
        velocity[start:end + 1] = segment_velocity
        acceleration[start:end + 1] = np.gradient(
            segment_velocity, times[start:end + 1], axis=0, edge_order=2
        )
    speed = np.linalg.norm(velocity, axis=1)
    heading = (np.degrees(np.arctan2(velocity[:, 0], velocity[:, 1])) + 360.0) % 360.0
    return velocity, acceleration, speed, heading


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data/urbantracker"))
    parser.add_argument("--config", type=Path, default=Path("configs/course_static.json"))
    parser.add_argument("--georeferencing", default="configs/georeferencing.json")
    parser.add_argument("--mask-file", type=Path, default=Path("data/urbantracker/masks/full_video.json"))
    parser.add_argument("--output", type=Path, default=Path("data/urbantracker/results/ground"))
    parser.add_argument("--heading-speed-threshold", type=float, default=0.5)
    args = parser.parse_args()

    config = read_json(args.config)
    geometry_config = settings(args.georeferencing)
    pixel_series, sources, _ = load_series(args.data_root, config)
    base = validate_saved_masks(read_json(args.mask_file), build_manifest(pixel_series, config, sources))
    root = project_path(args.data_root)
    projected_rows, calibration_sources = {}, {}
    for video in geometry_config["scenes"]:
        projected_path = root / "georeferenced" / video / "tracks_ground.csv"
        projection = read_json(projected_path.with_name("projection.json"))
        checks = {
            "calibration_sha256": sha256_file(
                Path(geometry_config["calibration_directory"])
                / (geometry_config["scenes"][video]["camera_id"] + ".json")
            ),
            "source_tracks_sha256": sha256_file(root / "tracks" / video / "tracks.csv"),
            "source_frames_sha256": sha256_file(root / "prepared" / video / "frames.csv"),
            "output_tracks_sha256": sha256_file(projected_path),
        }
        if any(projection.get(field) != digest for field, digest in checks.items()):
            raise ValueError(f"Projection data are stale for {video}; run project_ground first")
        calibration_sources.update({str(projected_path): checks["output_tracks_sha256"]})
        for row in read_csv(projected_path):
            projected_rows[(video, row["track_id"], int(row["frame"]))] = row

    metric_series, pixel_masks, metric_masks, excluded = calibrated_cases(
        pixel_series, base, projected_rows
    )
    if not metric_masks:
        raise ValueError("No calibrated masks available")

    masks_by_series = defaultdict(list)
    for mask in metric_masks:
        masks_by_series[mask["series_id"]].append(mask)
    reference_cache = {}
    rows = []
    for series_id, masks in masks_by_series.items():
        item = metric_series[series_id]
        reference_cache[series_id] = reference_kinematics(item["times"], item["positions"])
        ref_velocity, ref_acceleration, ref_speed, ref_heading = reference_cache[series_id]
        for mask in masks:
            visible = np.asarray(mask["visible_indices"])
            hidden = np.asarray(mask["hidden_indices"])
            query = item["times"][hidden]
            for method in config["methods"]:
                models = [
                    Interpolator(method).fit(item["times"][visible], item["positions"][visible, axis])
                    for axis in range(2)
                ]
                predicted_velocity = np.column_stack([model.derivative(query, 1) for model in models])
                predicted_acceleration = np.column_stack([model.derivative(query, 2) for model in models])
                predicted_speed = np.linalg.norm(predicted_velocity, axis=1)
                valid_heading = ref_speed[hidden] >= args.heading_speed_threshold
                heading_error = circular_error(
                    (np.degrees(np.arctan2(predicted_velocity[:, 0], predicted_velocity[:, 1])) + 360.0) % 360.0,
                    ref_heading[hidden],
                )
                rows.append({
                    "video_id": item["video_id"], "track_id": item["track_id"],
                    "mask_id": mask["mask_id"], "method": method, "gap_size": mask["gap_size"],
                    "speed_mae_mps": float(np.mean(np.abs(predicted_speed - ref_speed[hidden]))),
                    "acceleration_mae_mps2": float(np.mean(np.linalg.norm(
                        predicted_acceleration - ref_acceleration[hidden], axis=1))),
                    "heading_mae_deg": float(np.mean(heading_error[valid_heading]))
                    if valid_heading.any() else "",
                    "heading_valid": int(valid_heading.sum()),
                    "hidden_points": len(hidden),
                })

    aggregate = []
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["method"], row["gap_size"])].append(row)
    for (method, gap_size), group in sorted(grouped.items()):
        aggregate.append({
            "method": method, "gap_size": gap_size,
            "speed_mae_mps": float(np.mean([r["speed_mae_mps"] for r in group])),
            "acceleration_mae_mps2": float(np.mean([r["acceleration_mae_mps2"] for r in group])),
            "heading_mae_deg": float(np.mean([r["heading_mae_deg"] for r in group if r["heading_mae_deg"] != ""]))
            if any(r["heading_mae_deg"] != "" for r in group) else "",
            "heading_valid": sum(r["heading_valid"] for r in group),
            "masks": len(group),
        })
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "kinematic_metrics.csv", rows)
    write_csv(args.output / "kinematic_summary.csv", aggregate)
    write_json(args.output / "kinematic_run.json", {
        "valid_gap_count": len(metric_masks), "excluded_gap_count": len(excluded),
        "methods": config["methods"], "heading_speed_threshold_mps": args.heading_speed_threshold,
        "reference": "finite differences on complete projected YOLO/ByteTrack trajectories; not independent kinematic ground truth",
        "calibration_sha256": calibration_sources,
        "derivatives": "physical-time derivatives of interpolated east_m/north_m coordinates",
    })
    lines = [
        "# Kinematic evaluation", "",
        f"Metric gaps evaluated: **{len(metric_masks)}**; gaps excluded by calibration: {len(excluded)}.",
        "Derivatives are computed in physical time from the interpolated East and North coordinates.",
        "The reference is obtained with finite differences on the complete projected trajectory. It is a descriptive YOLO/ByteTrack-based estimate, not independent ground truth.",
        f"Heading is evaluated only when the reference speed is at least {args.heading_speed_threshold:.2f} m/s.",
        "", "| Method | Gap | Velocity MAE (m/s) | Acceleration MAE (m/s²) | Heading MAE (°) | Valid heading samples |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in aggregate:
        heading = f"{row['heading_mae_deg']:.4f}" if row["heading_mae_deg"] != "" else "n/a"
        lines.append(
            f"| {METHOD_LABELS[row['method']]} | {row['gap_size']} | {row['speed_mae_mps']:.5f} | "
            f"{row['acceleration_mae_mps2']:.5f} | {heading} | {row['heading_valid']} |"
        )
    (args.output / "KINEMATICS.md").write_text("\n".join(lines) + "\n")
    print(f"Kinematic benchmark complete: {len(rows)} mask-method evaluations")


if __name__ == "__main__":
    main()
