"""Project saved trajectories through real user calibrations; export metres and WGS84."""

import argparse
from pathlib import Path

import numpy as np

from .common import read_csv, read_json, sha256_file, write_csv, write_json
from .georeference import GroundCalibration, project_path, settings

WORLD_FIELDS = ("east_m", "north_m", "latitude_deg", "longitude_deg")


def project_record(model, pixel):
    try:
        return {**model.project(pixel), "projection_valid": True, "projection_reason": ""}
    except model.api.ProjectionError as error:
        return {**{field: "" for field in WORLD_FIELDS}, "projection_valid": False, "projection_reason": str(error)}


def project_sequence(video, model, root, grid_step, output):
    tracks_path = root / "tracks" / video / "tracks.csv"
    tracks_digest = sha256_file(tracks_path)
    tracks = read_csv(tracks_path)
    projected = []
    for row in tracks:
        projected.append({**row, **project_record(model, [float(row["x"]), float(row["y"])])})
    if not projected:
        raise ValueError(f"No tracked observations: {video}")
    if sha256_file(model.path) != model.calibration_sha256 or sha256_file(tracks_path) != tracks_digest:
        raise ValueError("Calibration or tracking changed during projection; rerun after saving has finished")
    write_csv(output / "tracks_ground.csv", projected)
    write_json(output / "calibration_snapshot.json", model.document)
    grid, features = [], []
    for y in range(0, model.height, grid_step):
        for x in range(0, model.width, grid_step):
            row = {"u_px": x, "v_px": y, **project_record(model, [x, y])}
            grid.append(row)
            if row["projection_valid"]:
                features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates":
                                 [row["longitude_deg"], row["latitude_deg"]]},
                                 "properties": {"u_px": x, "v_px": y, "east_m": row["east_m"], "north_m": row["north_m"]}})
    write_csv(output / "ground_grid.csv", grid)
    write_json(output / "ground_grid.geojson", {"type": "FeatureCollection", "features": features})
    valid = sum(row["projection_valid"] for row in projected)
    write_json(output / "projection.json", {
        "video_id": video, "calibration_path": str(model.path), "calibration_sha256": model.calibration_sha256,
        "source_tracks_sha256": tracks_digest,
        "source_frames_sha256": sha256_file(root / "prepared" / video / "frames.csv"),
        "output_tracks_sha256": sha256_file(output / "tracks_ground.csv"),
        "reference_observations": len(projected), "valid_observations": valid,
        "invalid_observations": len(projected) - valid,
        "axis_order": ["east_m", "north_m"], "geographic_order": ["latitude_deg", "longitude_deg"],
        "geojson_order": ["longitude", "latitude"],
        "fit_rms_m": model.document["rms_m"], "control_points": len(model.document["image_points"]),
        "inlier_control_points": sum(model.document["inlier_mask"]),
        "calibration_backend": str(model.api.__file__),
        "calibration_backend_sha256": sha256_file(model.api.__file__),
        "geometry_backend_sha256": sha256_file(model.geometry.__file__),
        "valid_image_polygon": model.document["valid_image_polygon"],
        "note": "Fit residual is not independent geographic accuracy; one ground plane inside the valid polygon",
    })
    print(f"{video}: {valid}/{len(projected)} osservazioni proiettate nella zona calibrata")


def check_independent_points(path, models, output):
    rows = []
    for point in read_csv(path):
        model = models[point["video_id"]]
        result = project_record(model, [float(point["u_px"]), float(point["v_px"])])
        error = ""
        if result["projection_valid"]:
            expected = model.local_coordinates([[float(point["latitude_deg"]), float(point["longitude_deg"])]])[0]
            error = float(np.linalg.norm(expected - [result["east_m"], result["north_m"]]))
        rows.append({**point, "projection_valid": result["projection_valid"], "projection_reason": result["projection_reason"],
                     "error_m": error})
    if not rows:
        raise ValueError("No independent checkpoints supplied")
    write_csv(output / "checkpoint_errors.csv", rows)
    valid = [row["error_m"] for row in rows if row["error_m"] != ""]
    write_json(output / "checkpoint_summary.json", {"supplied": len(rows), "valid": len(valid),
               "rms_m": float(np.sqrt(np.mean(np.square(valid)))) if valid else None,
               "policy": "checkpoints must be separate from fitting control points, supplied by the user"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/georeferencing.json")
    parser.add_argument("--data-root", type=Path, default=Path("data/urbantracker"))
    parser.add_argument("--grid-step", type=int, default=32)
    parser.add_argument("--checkpoints", type=Path)
    args = parser.parse_args()
    if args.grid_step < 1:
        parser.error("Grid step must be positive")
    root = project_path(args.data_root)
    config = settings(args.config)
    models = {}
    # Validate every scene before writing any projection output.
    for video in config["scenes"]:
        meta = read_json(root / "prepared" / video / "metadata.json")
        models[video] = GroundCalibration(config, video, meta["width"], meta["height"])
    for video, model in models.items():
        project_sequence(video, model, root, args.grid_step, root / "georeferenced" / video)
    if args.checkpoints:
        check_independent_points(project_path(args.checkpoints), models, root / "georeferenced")


if __name__ == "__main__":
    main()
