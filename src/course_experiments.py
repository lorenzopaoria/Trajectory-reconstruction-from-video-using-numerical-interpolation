"""Dedicated course experiments: Chebyshev/Runge, periodicity and support size."""

import argparse
import copy
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .benchmark import aggregate, evaluate, load_series
from .common import read_csv, read_json, sha256_file, write_csv, write_json
from .interpolation import Interpolator, NewtonPolynomial
from .methods import METHODS, plot_color


def chebyshev_experiment(output):
    grid = np.linspace(-1, 1, 2001)
    function = lambda t: 1 / (1 + 25 * t ** 2)
    reference = function(grid)
    rows, curves = [], {}
    for degree in (4, 8, 12, 16, 24, 32):
        for distribution in ("equispaced", "chebyshev_roots"):
            nodes = (np.linspace(-1, 1, degree + 1) if distribution == "equispaced" else
                     np.sort(np.cos((2 * np.arange(degree + 1) + 1) * np.pi / (2 * (degree + 1)))))
            # A mathematical polynomial is evaluated on the whole [-1,1] domain.
            # This synthetic approximation test deliberately includes the small
            # edge strips outside the Chebyshev roots, unlike the video gap adapter.
            prediction = NewtonPolynomial(nodes, function(nodes))(grid)
            errors = np.abs(prediction - reference)
            rows.append({
                "degree": degree, "n_nodes": len(nodes), "distribution": distribution,
                "max_error": float(errors.max()), "rms_error": float(np.sqrt(np.mean(errors ** 2))),
                "monomial_condition": float(np.linalg.cond(np.vander(nodes, increasing=True))),
                "evaluation_interval": "[-1,1]", "formulation": "Newton, float64",
            })
            if degree == 16:
                curves[distribution] = prediction
    write_csv(output / "chebyshev_runge.csv", rows)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(grid, reference, color="red", linewidth=3, label="Runge: riferimento")
    for name, color in (("equispaced", "#2878b5"), ("chebyshev_roots", "#36a657")):
        axes[0].plot(grid, curves[name], color=color, label=name)
        subset = [r for r in rows if r["distribution"] == name]
        axes[1].semilogy([r["degree"] for r in subset], [r["max_error"] for r in subset], "o-", color=color, label=name)
    axes[0].set(title="Grado 16: intero intervallo", xlabel="t", ylabel="Interpolante")
    axes[1].set(title="Errore massimo su [-1,1]", xlabel="Grado", ylabel="Errore massimo")
    for axis in axes:
        axis.grid(alpha=0.3)
        axis.legend()
    fig.tight_layout()
    fig.savefig(output / "chebyshev_runge.png", dpi=160)
    plt.close(fig)


def periodic_experiment(output):
    period = 6.0
    times = np.linspace(0, period, 49)
    phase = 2 * np.pi * times / period
    positions = np.column_stack((12 * np.cos(phase) + 1.5 * np.cos(2 * phase), 8 * np.sin(phase)))
    positions[-1] = positions[0]  # Analytically identical endpoints, not an imposed closure on real data.
    methods = ("s1", "s3_natural", "s3_periodic", "trigonometric")
    rows, examples = [], {}
    for start in (4, 20, 38):
        hidden = np.arange(start, start + 8)
        for method in methods:
            visible = np.setdiff1d(np.arange(len(times)), hidden)
            if method == "trigonometric":
                visible = visible[visible != len(times) - 1]  # Endpoint-exclusive Fourier convention.
            models = [Interpolator(method, period=period).fit(times[visible], positions[visible, axis])
                      for axis in range(2)]
            prediction = np.column_stack([model.predict(times[hidden]) for model in models])
            errors = np.linalg.norm(prediction - positions[hidden], axis=1)
            rows.append({"method": method, "gap_start": start, "gap_size": len(hidden),
                         "n_visible": len(visible), "period_s": period,
                         "ade": float(errors.mean()), "rms_position": float(np.sqrt(np.mean(errors ** 2))),
                         "fourier_matrix_condition": models[0].model.condition if method == "trigonometric" else ""})
            if start == 4:
                examples[method] = (hidden, prediction, errors)
    write_csv(output / "periodic.csv", rows)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(positions[:, 0], positions[:, 1], "r.-", label="Moto periodico esatto", linewidth=2)
    for method, (hidden, prediction, errors) in examples.items():
        axes[0].plot(prediction[:, 0], prediction[:, 1], "o-", color=plot_color(method), label=METHODS[method]["label"])
        axes[1].semilogy(times[hidden], np.maximum(errors, 1e-15), "o-", color=plot_color(method), label=METHODS[method]["label"])
    axes[0].set(title="Gap di 8 campioni, periodo noto", xlabel="x (unità sintetiche)", ylabel="y")
    axes[0].axis("equal")
    axes[1].set(title="Errore sui punti nascosti", xlabel="Tempo (s)", ylabel="Errore euclideo")
    for axis in axes:
        axis.grid(alpha=0.3)
        axis.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output / "periodic.png", dpi=160)
    plt.close(fig)


def support_experiment(data_root, config, mask_path, results, output):
    manifest = read_json(mask_path)
    series, sources, _ = load_series(data_root, config)
    if sources != manifest["source_sha256"]:
        raise ValueError("Source data changed since masks were created")
    combined = []
    for per_side in (2, 3):
        derived = copy.deepcopy(manifest)
        for mask in derived["masks"]:
            visible = mask["visible_indices"]
            split = len(visible) // 2
            mask["visible_indices"] = visible[split - per_side:split] + visible[split:split + per_side]
            frames = mask["visible_frames"]
            mask["visible_frames"] = frames[split - per_side:split] + frames[split:split + per_side]
        derived["support_study"] = {"source_mask_sha256": sha256_file(mask_path), "nodes_per_side": per_side,
                                    "policy": "nearest visible nodes, same hidden observations"}
        write_json(output / f"masks_support_{2 * per_side}.json", derived)
        metrics, predictions = evaluate(series, derived, config["methods"])
        del predictions
        summary = aggregate(metrics)
        del metrics
        combined.extend(dict(row, support_nodes=2 * per_side) for row in summary)
    combined.extend(dict(row, support_nodes=8) for row in read_csv(results / "summary.csv"))
    write_csv(output / "support_study.csv", combined)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data/urbantracker"))
    parser.add_argument("--config", type=Path, default=Path("configs/course_static.json"))
    parser.add_argument("--mask-file", type=Path, default=Path("data/urbantracker/masks/full_video.json"))
    parser.add_argument("--results", type=Path, default=Path("data/urbantracker/results/course"))
    parser.add_argument("--output", type=Path, default=Path("reports/generated/course/experiments"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    chebyshev_experiment(args.output)
    periodic_experiment(args.output)
    support_experiment(args.data_root, read_json(args.config), args.mask_file, args.results, args.output)
    write_json(args.output / "experiment_notes.json", {
        "chebyshev": "Exact roots, n+1 nodes for degree n; Runge on [-1,1]; no resampling of hidden video data",
        "periodic": "Analytic closed trajectory, known period; natural/periodic splines and Fourier linear system; no FFT on incomplete data",
        "support": "4/6/8 visible nodes, same hidden samples; exact polynomial degree at most 3/5/7",
        "metrics": "Synthetic units and video pixels are separate; timings are descriptive single-fit measurements",
    })
    print(f"Course experiments saved: {args.output}")


if __name__ == "__main__":
    main()
