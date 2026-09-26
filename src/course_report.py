"""Summarize all course experiments and optionally decode-check every short clip."""

import argparse
import csv
import itertools
import json
from pathlib import Path
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .common import read_csv, read_json, sha256_file, write_csv, write_json
from .methods import METHODS, POLYNOMIAL_METHODS, plot_color


def polynomial_agreement(path):
    stats = {name: {"points": 0, "max_difference_px": 0.0, "squared_sum": 0.0}
             for name in ("lagrange", "newton")}
    with path.open(newline="") as source:
        for _, group in itertools.groupby(csv.DictReader(source), key=lambda row: row["mask_id"]):
            points = {method: {} for method in POLYNOMIAL_METHODS}
            for row in group:
                if row["method"] in points:
                    points[row["method"]][row["frame"]] = np.array([float(row["predicted_x"]), float(row["predicted_y"])])
            baseline = points["vandermonde"]
            for method, accumulator in stats.items():
                for frame in baseline.keys() & points[method].keys():
                    distance = float(np.linalg.norm(baseline[frame] - points[method][frame]))
                    accumulator["points"] += 1
                    accumulator["squared_sum"] += distance ** 2
                    accumulator["max_difference_px"] = max(accumulator["max_difference_px"], distance)
    rows = []
    for method, value in stats.items():
        rows.append({"reference_formulation": "vandermonde", "other_formulation": method,
                     "compared_points": value["points"], "max_difference_px": value["max_difference_px"],
                     "rms_difference_px": float(np.sqrt(value["squared_sum"] / value["points"])) if value["points"] else ""})
    return rows


def verify_clips(root, manifest):
    checked = []
    for clip in manifest:
        path = root / clip["filename"]
        if sha256_file(path) != clip["video_sha256"]:
            raise ValueError(f"Video checksum mismatch: {path}")
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-threads", "2", "-count_frames", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,nb_read_frames:format=duration", "-of", "json", str(path),
        ], check=True, capture_output=True, text=True)
        info = json.loads(probe.stdout)
        stream = info["streams"][0]
        if (int(stream["nb_read_frames"]) != clip["encoded_frames"]
                or stream["width"] != clip["width"] or stream["height"] != clip["height"]
                or stream["codec_name"] != "h264"):
            raise ValueError(f"Unexpected encoded video properties: {path}")
        checked.append({"filename": clip["filename"], "decoded_frames": int(stream["nb_read_frames"]),
                        "duration_s": float(info["format"]["duration"]), "checksum_ok": True})
    return checked


def figures(summary, support, methods, output):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for method in methods:
        rows = sorted((r for r in summary if r["method"] == method and r["micro_ade"]), key=lambda r: int(r["gap_size"]))
        axes[0].plot([int(r["gap_size"]) for r in rows], [float(r["micro_ade"]) for r in rows],
                     "o-", label=METHODS[method]["label"], color=plot_color(method))
        rows = sorted((r for r in support if r["method"] == method and int(r["gap_size"]) == 24 and r["micro_ade"]),
                      key=lambda r: int(r["support_nodes"]))
        axes[1].plot([int(r["support_nodes"]) for r in rows], [float(r["micro_ade"]) for r in rows],
                     "o-", label=METHODS[method]["label"], color=plot_color(method))
    axes[0].set(title="8 nodi visibili: errore medio", xlabel="Frame nascosti", ylabel="ADE (pixel)")
    axes[1].set(title="Stessi gap di 24 frame, supporto variabile", xlabel="Nodi visibili", ylabel="ADE (pixel)")
    axes[1].set_xticks([4, 6, 8])
    for axis in axes:
        axis.grid(alpha=0.3)
        axis.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output / "course_comparison.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("data/urbantracker/results/course"))
    parser.add_argument("--output", type=Path, default=Path("reports/generated/course"))
    parser.add_argument("--verify-clips", action="store_true")
    args = parser.parse_args()
    run = read_json(args.results / "run.json")
    summary = read_csv(args.results / "summary.csv")
    support = read_csv(args.output / "experiments" / "support_study.csv")
    clips = read_json(args.output / "clips" / "manifest.json")
    agreement = polynomial_agreement(args.results / "predictions.csv")
    write_csv(args.output / "polynomial_agreement.csv", agreement)
    figures(summary, support, run["config"]["methods"], args.output)
    if args.verify_clips:
        checks = verify_clips(args.output / "clips", clips)
        write_json(args.output / "clip_validation.json", checks)
        print(f"Verified {len(checks)} clips, {sum(c['decoded_frames'] for c in checks)} decoded frames")
    lines = [
        "# Confronto dei metodi del corso e clip dei passaggi", "",
        f"- {len(run['config']['methods'])} metodi nel benchmark stradale, {run['mask_count']} gap, {run['evaluations']} valutazioni.",
        f"- Fallimenti numerici: {run['failed_evaluations']}; maschere salvate riutilizzate: {run['reused_saved_masks']}.",
        f"- {len(clips)} clip di passaggi, durata {min(c['duration_s'] for c in clips):.2f}–{max(c['duration_s'] for c in clips):.2f} s, codificate con NVENC.",
        "- Ogni clip: riferimento YOLO/ByteTrack rosso acceso, zoom fisso e un riquadro per interpolatore.",
        "- Le clip sono illustrative e selezionate per movimento e distribuzione temporale, indipendentemente dagli errori. Le metriche coprono tutti i casi ammissibili dei video completi.",
        "", "**[Apri l'indice delle clip](clips/INDEX.md)**", "",
        "## Metodi", "",
        "Vandermonde (sistema monomiale), Lagrange (formula diretta), Newton (differenze divise e Horner), S1, S3 naturale e S3 vincolata costituiscono il nucleo trattato nelle slide.",
        "La S3 vincolata stima le derivate ai bordi dai primi/ultimi tre campioni visibili. Non usa velocità ricavate dai punti nascosti.",
        "S2 è un'estensione dalla definizione generale di spline. La famiglia razionale è introdotta nelle slide; la specifica costruzione Floater–Hormann, parametro d=3, è un'estensione esterna esplicitamente indicata.",
        "", "## Risultati sui video, 8 nodi", "",
        "| Metodo | Gap | ADE (px) | RMS (px) | Fit mediano (ms) | Fallimenti |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        formatted = [f"{float(row[key]):.4f}" if row[key] else "n/a"
                     for key in ("micro_ade", "micro_rms_position", "median_fit_ms")]
        lines.append(f"| {METHODS[row['method']]['label']} | {row['gap_size']} | "
                     + " | ".join(formatted) + f" | {row['failed_masks']} |")
    lines += ["", "I tempi sono misure descrittive di singoli fit, aggregate su molte prove; includono le due coordinate. Il calcolo del condizionamento è escluso dall'intervallo cronometrato.",
              "Il condizionamento esportato si riferisce alla matrice monomiale sul tempo normalizzato, non a ogni famiglia di interpolatori. L'eccesso rispetto al rettangolo dei nodi di supporto è un indicatore geometrico, non un errore fisico.",
              "", "![Confronto](course_comparison.png)", "",
              "## Equivalenza delle formulazioni polinomiali", ""]
    for row in agreement:
        lines.append(f"- Vandermonde / {row['other_formulation']}: {row['compared_points']} punti confrontati, "
                     f"differenza euclidea massima **{row['max_difference_px']:.3e} pixel**.")
    lines += ["", "Con gli stessi nodi i tre metodi rappresentano lo stesso polinomio. Le oscillazioni rispetto al riferimento non si risolvono semplicemente passando da una formulazione all'altra.",
              "", "## Esperimenti dedicati", "",
              "- **Chebyshev/Runge:** gradi 4, 8, 12, 16, 24 e 32; n+1 nodi equispaziati o radici esatte di Chebyshev. Valutazione matematica su [-1,1], comprese le piccole fasce esterne alle radici; nessun accesso ai dati video nascosti.",
              "- **Periodicità:** traiettoria analitica chiusa con periodo noto; S3 periodica e interpolazione trigonometrica confrontate con S1 e S3 naturale. Per i campioni mancanti si risolve il sistema trigonometrico, non si applica direttamente una FFT alla griglia incompleta.",
              "- **Supporto:** 4, 6 e 8 osservazioni visibili sugli stessi punti nascosti. Per i polinomi corrispondono a gradi massimi 3, 5 e 7. Le maschere derivate mantengono l'esclusione globale dei campioni nascosti.",
              "", "![Chebyshev](experiments/chebyshev_runge.png)", "", "![Periodicità](experiments/periodic.png)", "",
              "La trigonometrica può riprodurre quasi esattamente il segnale sintetico perché questo appartiene alla base scelta. Ciò non dimostra superiorità sui video di traffico non periodici.",
              "Le ricostruzioni stradali sono riferite a output YOLO/ByteTrack post-tracking, non a posizioni fisiche esatte o identità manualmente validate."]
    (args.output / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print(f"Course report: {args.output / 'RESULTS.md'}")
    for row in agreement:
        print(row)


if __name__ == "__main__":
    main()
