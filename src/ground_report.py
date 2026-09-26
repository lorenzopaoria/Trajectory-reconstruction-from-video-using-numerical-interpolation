"""Plot calibrated road zones and the metric benchmark, using published data only."""

import argparse
from collections import Counter
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .common import read_csv, read_json, sha256_file, write_json
from .georeference import project_path, settings
from .methods import METHODS, plot_color


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/georeferencing.json")
    parser.add_argument("--data-root", type=Path, default=Path("data/urbantracker"))
    parser.add_argument("--output", type=Path, default=Path("reports/generated/ground"))
    args = parser.parse_args()
    config = settings(args.config)
    root = project_path(args.data_root)
    args.output.mkdir(parents=True, exist_ok=True)
    cv2.setNumThreads(1)
    run = read_json(root / "results" / "ground" / "run.json")
    mask_counts = Counter(mask["series_id"].split("/")[1]
                          for mask in read_json(root / "results" / "ground" / "metric_masks.json")["masks"])
    for path, digest in run["calibration_sha256"].items():
        if sha256_file(path) != digest:
            raise ValueError(f"Input changed since metric benchmark: {path}")
    diagnostics = []
    fig, axes = plt.subplots(1, len(config["scenes"]), figsize=(14, 5), squeeze=False)
    for axis, (video, scene) in zip(axes[0], config["scenes"].items()):
        meta = read_json(root / "georeferenced" / video / "projection.json")
        document = read_json(root / "georeferenced" / video / "calibration_snapshot.json")
        capture = cv2.VideoCapture(str(project_path(scene["source"])))
        try:
            capture.set(cv2.CAP_PROP_POS_MSEC, 1500)
            ok, image = capture.read()
        finally:
            capture.release()
        if not ok:
            raise ValueError(f"Cannot read source frame: {video}")
        h, w = image.shape[:2]
        polygon = np.rint(np.array(document["valid_image_polygon"]) * [w, h]).astype(np.int32)
        overlay = image.copy()
        cv2.fillPoly(overlay, [polygon], (60, 200, 50))
        image = cv2.addWeighted(image, 0.75, overlay, 0.25, 0)
        cv2.polylines(image, [polygon], True, (40, 255, 30), 2)
        points = np.rint(np.array(document["image_points"]) * [w, h]).astype(int)
        for index, (point, inlier) in enumerate(zip(points, document["inlier_mask"]), 1):
            color = (0, 240, 80) if inlier else (0, 80, 255)
            cv2.circle(image, tuple(point), 6, color, -1)
            cv2.putText(image, str(index), (int(point[0]) + 8, int(point[1]) - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(image, str(index), (int(point[0]) + 8, int(point[1]) - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.imwrite(str(args.output / f"calibration_{video}.png"), image)
        axis.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        axis.set_title(f"{video}: {sum(document['inlier_mask'])}/{len(points)} punti inlier\n"
                       f"{meta['valid_observations']}/{meta['reference_observations']} osservazioni nella zona valida")
        axis.axis("off")
        diagnostics.append({"video_id": video, "control_points": len(points), "inliers": sum(document["inlier_mask"]),
                            "fit_rms_m": document["rms_m"], "valid_observations": meta["valid_observations"],
                            "total_observations": meta["reference_observations"], "valid_gaps": mask_counts[video]})
    fig.suptitle("Poligono calibrato: verde. Punti esclusi dal fit robusto: arancio.")
    fig.tight_layout()
    fig.savefig(args.output / "calibration_coverage.png", dpi=160)
    plt.close(fig)

    summary = read_csv(root / "results" / "ground" / "summary.csv")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for axis, kind, label in zip(axes, ("object_pixels", "object_ground"), ("pixel", "metri")):
        for method in run["methods"]:
            rows = sorted((r for r in summary if r["kind"] == kind and r["method"] == method and r["micro_ade"]),
                          key=lambda r: int(r["gap_size"]))
            axis.plot([int(r["gap_size"]) for r in rows], [float(r["micro_ade"]) for r in rows],
                      "o-", label=METHODS[method]["label"], color=plot_color(method))
        axis.set(title=f"Stessi {run['valid_gap_count']} gap: fit in {label}", xlabel="Frame nascosti", ylabel=f"ADE ({label})")
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(args.output / "metric_comparison.png", dpi=160)
    plt.close(fig)
    write_json(args.output / "calibration_summary.json", {"calibrations": diagnostics, **run})
    lines = ["# Piano stradale calibrato: primo confronto metrico", "",
             f"Gap validi: **{run['valid_gap_count']}/{run['base_gap_count']}**; esclusi: {run['excluded_gap_count']}.",
             "Il dominio valido copre una parte dei filmati, non tutta l'immagine. Le osservazioni esterne sono escluse.",
             "La baseline in pixel usa gli stessi gap ammessi dal confronto in metri.", "",
             "## Calibrazioni", "", "| Scena | Punti | Inlier | RMS del fit (m) | Osservazioni valide |",
             "|---|---:|---:|---:|---:|"]
    for d in diagnostics:
        lines.append(f"| {d['video_id']} | {d['control_points']} | {d['inliers']} | {d['fit_rms_m']:.6g} | {d['valid_observations']} / {d['total_observations']} |")
    lines += ["", "Il residuo del fit non è una misura indipendente di accuratezza. Con quattro punti può essere quasi nullo.",
              "Non sono ancora stati forniti punti indipendenti di verifica in questo run.", "",
              "![Copertura](calibration_coverage.png)", "", "![Confronto](metric_comparison.png)", "",
              "## Risultati metrici", "", "| Metodo | Gap | ADE (m) | RMS (m) |", "|---|---:|---:|---:|"]
    for row in summary:
        if row["kind"] == "object_ground":
            ade = f"{float(row['micro_ade']):.5f}" if row["micro_ade"] else "n/a"
            rms = f"{float(row['micro_rms_position']):.5f}" if row["micro_rms_position"] else "n/a"
            lines.append(f"| {METHODS[row['method']]['label']} | {row['gap_size']} | {ade} | {rms} |")
    lines += ["", "Il riferimento è YOLO/ByteTrack proiettato tramite omografia, non un GPS indipendente delle auto. La valutazione cinematica è riportata separatamente in KINEMATICS.md."]
    (args.output / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print(f"Metric report: {args.output / 'RESULTS.md'}")


if __name__ == "__main__":
    main()
