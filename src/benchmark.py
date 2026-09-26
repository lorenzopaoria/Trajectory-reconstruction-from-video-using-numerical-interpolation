"""Urban traffic benchmark: identical held-out frames/support for every method."""

import argparse
from collections import defaultdict
import hashlib
import importlib.metadata
from pathlib import Path
import platform
import time

import numpy as np

from .common import read_csv, read_json, sha256_file, write_csv, write_json
from .gaps import make_continuous_masks, make_masks
from .interpolation import Interpolator
from .methods import METHODS, POLYNOMIAL_METHODS


def load_series(data_root, config):
    series = {}
    sources = {}
    selection = []
    for path in sorted((data_root / "prepared").glob("*/frames.csv")):
        sources[str(path)] = sha256_file(path)
    for path in sorted((data_root / "tracks").glob("*/tracks.csv")):
        sources[str(path)] = sha256_file(path)
        groups = defaultdict(list)
        for row in read_csv(path):
            groups[row["track_id"]].append(row)
        for track_id, rows in sorted(groups.items()):
            rows.sort(key=lambda row: int(row["frame"]))
            video = path.parent.name
            positions = np.array([[float(r["x"]), float(r["y"])] for r in rows])
            geometry = np.array([[float(r["w"]), float(r["h"])] for r in rows])
            confidence = float(np.mean([float(r["confidence"]) for r in rows]))
            reason = "selected"
            if len(rows) < config["minimum_track_frames"]:
                reason = "too_short"
            elif config.get("allowed_class_ids") is not None and any(
                    int(r["class_id"]) not in config["allowed_class_ids"] for r in rows):
                reason = "excluded_class"
            elif not np.isfinite(positions).all() or not np.isfinite(geometry).all() or np.any(geometry <= 0):
                reason = "invalid_geometry"
            elif confidence < config["minimum_mean_confidence"]:
                reason = "low_mean_confidence"
            elif len({r["class_id"] for r in rows}) != 1:
                reason = "inconsistent_class"
            elif np.linalg.norm(np.ptp(positions, axis=0)) < config["minimum_displacement_px"]:
                reason = "insufficient_image_motion"
            selection.append({
                "video_id": video, "track_id": track_id, "observations": len(rows),
                "mean_confidence": confidence, "class_name": rows[0]["class_name"], "status": reason,
            })
            if reason != "selected":
                continue
            key = f"object_pixels/{video}/{track_id}"
            series[key] = {
                "video_id": video, "kind": "object_pixels", "track_id": track_id, "unit": "px",
                "frames": np.array([int(r["frame"]) for r in rows]),
                "times": np.array([float(r["timestamp_s"]) for r in rows]), "positions": positions,
            }
    if not series:
        raise ValueError("No usable tracks; prepare Urban Tracker and run tracking first")
    return series, sources, selection


def build_manifest(series, config, sources):
    masks = []
    for key, item in sorted(series.items()):
        identity_seed = int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big")
        seed = config["seed"] + identity_seed
        if config.get("masking_mode") == "continuous":
            candidates = make_continuous_masks(
                item["frames"], item["times"], config["gap_sizes"], config["support_per_side"], seed,
            )
        else:
            candidates = make_masks(
                item["frames"], item["times"], config["gap_sizes"], config["support_per_side"],
                config["masks_per_gap_per_track"], seed,
            )
        for index, mask in enumerate(candidates):
            mask.update({"series_id": key, "mask_id": f"{key}/mask_{index:04d}"})
            masks.append(mask)
    if not masks:
        raise ValueError("No eligible internal gaps with the configured support")
    return {
        "schema_version": 1, "config": config, "source_sha256": sources,
        "rng": "NumPy default_rng / PCG64; seed derived from base seed and series identity",
        "independence": ("Single schedule per track; hidden sets disjoint; shared visible anchors; not independent trials"
                         if config.get("masking_mode") == "continuous" else
                         "Each mask is a separate trial; windows may overlap across trials"),
        "masks": masks,
    }


def validate_saved_masks(saved, candidate):
    """Changing methods may reuse a manifest; changing its actual cases may not."""
    if (saved.get("source_sha256") != candidate.get("source_sha256")
            or saved.get("masks") != candidate.get("masks")):
        raise ValueError("Existing masks refer to different data or cases. Choose a new --mask-file.")
    return saved


def evaluate(series, manifest, methods):
    metrics, predictions = [], []
    for mask in manifest["masks"]:
        item = series[mask["series_id"]]
        visible = np.array(mask["visible_indices"])
        hidden = np.array(mask["hidden_indices"])
        query = item["times"][hidden]
        support = item["times"][visible]
        tau = 2 * (support - support[0]) / (support[-1] - support[0]) - 1
        # Diagnostic outside the timed fit; this is a monomial-system condition,
        # not a basis-independent condition number of every interpolation method.
        condition = float(np.linalg.cond(np.vander(tau, len(tau), increasing=True)))
        for method in methods:
            record = {
                "kind": item["kind"], "unit": item["unit"], "video_id": item["video_id"],
                "track_id": item["track_id"], "mask_id": mask["mask_id"], "method": method,
                "gap_size": mask["gap_size"], "bracket_duration_s": mask["bracket_duration_s"],
                "n_points": len(hidden), "n_valid": 0, "status": "failed", "failure": "",
                "ade": "", "rms_position": "", "max_error": "", "squared_error_sum": "",
                "fit_ms": "", "evaluate_ms": "",
                "monomial_condition": condition if method in POLYNOMIAL_METHODS else "",
                "polynomial_degree_at_most": len(visible) - 1 if method in POLYNOMIAL_METHODS else "",
                "max_support_box_excess": "",
            }
            try:
                start = time.perf_counter()
                # Only visible values reach fit; both coordinates use the identical support.
                models = [Interpolator(method).fit(
                    item["times"][visible], item["positions"][visible, axis],
                ) for axis in range(2)]
                fitted = time.perf_counter()
                estimate = np.column_stack([model.predict(query) for model in models])
                evaluated = time.perf_counter()
                if not np.isfinite(estimate).all():
                    raise FloatingPointError("Nonfinite interpolated coordinates")
                # The held-out reference is read for scoring only after prediction.
                reference = item["positions"][hidden]
                errors = np.linalg.norm(estimate - reference, axis=1)
                observed = item["positions"][visible]
                excess = np.maximum(observed.min(axis=0) - estimate, 0) + np.maximum(estimate - observed.max(axis=0), 0)
                record.update({
                    "n_valid": len(hidden), "status": "ok", "ade": float(errors.mean()),
                    "rms_position": float(np.sqrt(np.mean(errors ** 2))),
                    "max_error": float(errors.max()), "squared_error_sum": float(np.sum(errors ** 2)),
                    "fit_ms": 1000 * (fitted - start), "evaluate_ms": 1000 * (evaluated - fitted),
                    "max_support_box_excess": float(np.linalg.norm(excess, axis=1).max()),
                })
                for j, source_index in enumerate(hidden):
                    predictions.append({
                        "kind": item["kind"], "unit": item["unit"], "video_id": item["video_id"],
                        "track_id": item["track_id"], "mask_id": mask["mask_id"], "method": method,
                        "gap_size": mask["gap_size"], "frame": int(item["frames"][source_index]),
                        "timestamp_s": float(query[j]),
                        "reference_x": float(reference[j, 0]), "reference_y": float(reference[j, 1]),
                        "predicted_x": float(estimate[j, 0]), "predicted_y": float(estimate[j, 1]),
                        "position_error": float(errors[j]),
                    })
            except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
                record["failure"] = str(error)
            metrics.append(record)
    return metrics, predictions


def aggregate(metrics):
    groups = defaultdict(list)
    for row in metrics:
        groups[(row["kind"], row["unit"], row["method"], row["gap_size"])].append(row)
    summary = []
    for (kind, unit, method, gap), rows in sorted(groups.items()):
        valid = [r for r in rows if r["status"] == "ok"]
        n_valid = sum(r["n_valid"] for r in rows)
        n_total = sum(r["n_points"] for r in rows)
        tracks = defaultdict(list)
        for row in valid:
            tracks[(row["video_id"], row["track_id"])].append(row["ade"])

        def statistic(field, operation):
            values = [float(r[field]) for r in valid if r.get(field) not in (None, "")]
            return float(operation(values)) if values else ""

        summary.append({
            "kind": kind, "unit": unit, "method": method, "gap_size": gap,
            "n_masks": len(rows), "failed_masks": len(rows) - len(valid),
            "n_points": n_total, "n_valid": n_valid, "coverage": n_valid / n_total,
            "n_videos": len({r["video_id"] for r in rows}),
            "n_tracks": len({(r["video_id"], r["track_id"]) for r in rows}),
            "micro_ade": sum(r["ade"] * r["n_valid"] for r in valid) / n_valid if n_valid else "",
            "micro_rms_position": float(np.sqrt(sum(r["squared_error_sum"] for r in valid) / n_valid)) if n_valid else "",
            "macro_gap_ade": float(np.mean([r["ade"] for r in valid])) if valid else "",
            "macro_track_ade": float(np.mean([np.mean(values) for values in tracks.values()])) if tracks else "",
            "median_fit_ms": statistic("fit_ms", np.median),
            "median_evaluate_ms": statistic("evaluate_ms", np.median),
            "max_monomial_condition": statistic("monomial_condition", np.max),
            "max_support_box_excess": statistic("max_support_box_excess", np.max),
        })
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data/urbantracker"))
    parser.add_argument("--config", type=Path, default=Path("configs/course_static.json"))
    parser.add_argument("--mask-file", type=Path, default=Path("data/urbantracker/masks/full_video.json"))
    parser.add_argument("--output", type=Path, default=Path("data/urbantracker/results/course"))
    args = parser.parse_args()
    config = read_json(args.config)
    if any(method not in METHODS for method in config["methods"]):
        parser.error("Unknown interpolation method in configuration")
    series, sources, selection = load_series(args.data_root, config)
    manifest = build_manifest(series, config, sources)
    reused = args.mask_file.exists()
    if reused:
        manifest = validate_saved_masks(read_json(args.mask_file), manifest)
    else:
        # Persist before fitting anything; never rewrite a compatible saved manifest.
        write_json(args.mask_file, manifest)
    metrics, predictions = evaluate(series, manifest, config["methods"])
    if not predictions:
        raise ValueError("Every reconstruction failed")
    write_csv(args.output / "metrics.csv", metrics)
    write_csv(args.output / "predictions.csv", predictions)
    summary = aggregate(metrics)
    write_csv(args.output / "summary.csv", summary)
    if selection:
        write_csv(args.output / "track_selection.csv", selection)
    write_json(args.output / "run.json", {
        "config": config, "mask_file": str(args.mask_file),
        "mask_sha256": sha256_file(args.mask_file), "source_sha256": sources,
        "reused_saved_masks": reused,
        "methods": {name: METHODS[name] for name in config["methods"]},
        "series_count": len(series), "mask_count": len(manifest["masks"]),
        "evaluations": len(metrics), "failed_evaluations": sum(r["status"] != "ok" for r in metrics),
        "reference_types": {"object_pixels": "YOLO/ByteTrack pseudo-reference"},
        "s2_boundary": "second derivative of first interval is zero",
        "s3_clamped_boundary": "endpoint derivatives from local quadratics through first/last 3 visible samples",
        "rational": "Floater-Hormann, d=min(3, number_of_nodes-1); extension of the introduced rational family",
        "polynomials": "same degree-at-most-(n-1) polynomial on n visible nodes, three independent implementations",
        "code_sha256": {name: sha256_file(Path(__file__).with_name(name)) for name in (
            "interpolation.py", "benchmark.py", "gaps.py", "methods.py",
        )},
        "python": platform.python_version(),
        "versions": {p: importlib.metadata.version(p) for p in ("numpy", "scipy")},
        "interpretation": manifest["independence"] + "; descriptive evaluation; no validation/test claims",
    })
    print(f"Saved {len(manifest['masks'])} masks, {len(metrics)} evaluations, {len(predictions)} predictions")
    for row in summary:
        print(f"{row['kind']:14} {row['method']:12} gap={row['gap_size']:2} "
              f"ADE={row['micro_ade']!s:>12} {row['unit']}, failures={row['failed_masks']}")


if __name__ == "__main__":
    main()
