"""Render every frame and every scheduled car gap, using NVIDIA NVENC by default."""

import argparse
from collections import defaultdict, deque
from pathlib import Path
import subprocess

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .common import read_csv, read_json, sha256_file, write_csv, write_json
from .video_frames import iter_frames

METHODS = ("s1", "s2", "s3_natural")
COLORS = {"s1": (255, 160, 30), "s2": (0, 150, 255), "s3_natural": (220, 60, 190)}
PLOT_COLORS = {"s1": "#1f77b4", "s2": "#ff7f0e", "s3_natural": "#9467bd"}


def render(video_id, masks, predictions, root, output, encoder_name):
    frames = read_csv(root / "prepared" / video_id / "frames.csv")
    metadata = read_json(root / "prepared" / video_id / "metadata.json")
    references = defaultdict(dict)
    for row in read_csv(root / "tracks" / video_id / "tracks.csv"):
        references[int(row["frame"])][row["track_id"]] = row
    hidden = defaultdict(set)
    for mask in masks:
        track_id = mask["series_id"].rsplit("/", 1)[1]
        for frame in mask["hidden_frames"]:
            if track_id in hidden[frame]:
                raise ValueError("Overlapping gaps cannot be rendered as one consistent schedule")
            hidden[frame].add(track_id)
    estimates = {}
    for row in predictions:
        estimates[(int(row["frame"]), row["track_id"], row["method"])] = (
            float(row["predicted_x"]), float(row["predicted_y"]),
        )

    rows = iter_frames(frames)
    first_row, first_image = next(rows)
    height, width = first_image.shape[:2]
    band = 100
    destination = output / f"full_reconstruction_{video_id}.mp4"
    encoding = (["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "21", "-b:v", "0"]
                if encoder_name == "h264_nvenc" else ["-c:v", "libx264", "-preset", "fast", "-crf", "21"])
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
        "-pixel_format", "bgr24", "-video_size", f"{width}x{height + band}",
        "-framerate", str(metadata["preview_fps"]), "-i", "pipe:0",
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", *encoding,
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination),
    ]
    trails = defaultdict(lambda: deque(maxlen=35))
    last_seen = {}
    timeline = []
    snapshots = {len(frames) // 4, len(frames) // 2, 3 * len(frames) // 4}
    import itertools
    with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
        try:
            for frame, image in itertools.chain([(first_row, first_image)], rows):
                index = int(frame["frame"])
                if image.shape[:2] != (height, width):
                    raise ValueError("Changing video dimensions")
                active = references.get(index, {})
                masked_tracks = hidden.get(index, set())
                if not masked_tracks.issubset(active):
                    raise ValueError("Masked sample has no saved reference box")
                for track_id, ref in active.items():
                    masked = track_id in masked_tracks
                    point = (float(ref["x"]), float(ref["y"]))
                    if last_seen.get(track_id) != index - 1:
                        for method in METHODS:
                            trails[(track_id, method)].clear()
                    last_seen[track_id] = index
                    for method in METHODS:
                        estimate = estimates.get((index, track_id, method)) if masked else point
                        if estimate is None:
                            trails[(track_id, method)].clear()
                            continue
                        # The current reference is never substituted for a failed hidden prediction.
                        trails[(track_id, method)].append(estimate)
                        line = np.array(trails[(track_id, method)], dtype=np.int32)
                        if len(line) > 1:
                            cv2.polylines(image, [line], False, COLORS[method], 1)
                        if masked:
                            cv2.circle(image, tuple(np.rint(estimate).astype(int)), 5, COLORS[method], 2)
                    color = (40, 40, 240) if masked else (40, 190, 40)
                    x1, y1, x2, y2 = (round(float(ref[k])) for k in ("x_min", "y_min", "x_max", "y_max"))
                    cv2.rectangle(image, (x1, y1), (x2, y2), color, 1)
                    cv2.circle(image, tuple(np.rint(point).astype(int)), 2, color, -1)
                    cv2.putText(image, f"{'REF' if masked else 'OBS'} {track_id}", (x1, max(12, y1 - 4)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)
                banner = np.full((band, width, 3), 20, dtype=np.uint8)
                lines = [
                    f"{video_id} | FIXED CAMERA | frame {index + 1}/{len(frames)} | t={float(frame['timestamp_s']):.2f}s",
                    f"CARS | visible: {len(active) - len(masked_tracks)} | hidden/reconstructed: {len(masked_tracks)} | OFFLINE",
                    "Green boxes: observed | Red boxes: held-out reference | Colored points/trails: reconstructed positions",
                ]
                for j, text in enumerate(lines):
                    cv2.putText(banner, text, (8, 19 + 23 * j), cv2.FONT_HERSHEY_SIMPLEX,
                                min(0.47, width / 1950), (230, 230, 230), 1)
                for j, method in enumerate(METHODS):
                    cv2.putText(banner, method, (8 + 170 * j, 89), cv2.FONT_HERSHEY_SIMPLEX, 0.48, COLORS[method], 1)
                canvas = np.vstack((banner, image))
                if index in snapshots:
                    cv2.imwrite(str(output / f"snapshot_{video_id}_{index:05d}.jpg"), canvas)
                encoder.stdin.write(canvas.tobytes())
                timeline.append({"video_id": video_id, "frame": index, "timestamp_s": float(frame["timestamp_s"]),
                                 "reference_cars": len(active), "hidden_cars": len(masked_tracks)})
                if (index + 1) % 1000 == 0 or index + 1 == len(frames):
                    print(f"NVENC render {video_id}: {index + 1}/{len(frames)}", flush=True)
        finally:
            encoder.stdin.close()
            rows.close()
        if encoder.wait() != 0:
            raise RuntimeError("Video encoder failed")
    write_csv(output / f"timeline_{video_id}.csv", timeline)
    masked_frames = [r["frame"] for r in timeline if r["hidden_cars"]]
    return {
        "video_id": video_id, "encoded_frames": len(timeline), "source_frames": len(frames),
        "encoder": encoder_name, "full_video": len(timeline) == len(frames),
        "duration_between_first_last_s": float(frames[-1]["timestamp_s"]),
        "frames_with_cars": sum(r["reference_cars"] > 0 for r in timeline),
        "frames_with_reconstruction": len(masked_frames),
        "first_reconstructed_frame": min(masked_frames) if masked_frames else None,
        "last_reconstructed_frame": max(masked_frames) if masked_frames else None,
        "hidden_car_observations": sum(r["hidden_cars"] for r in timeline),
        "masks": len(masks), "reconstructed_tracks": len({m["series_id"] for m in masks}),
        "video": str(destination), "sha256": sha256_file(destination),
    }, timeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data/urbantracker"))
    parser.add_argument("--results", type=Path, default=Path("data/urbantracker/results/full_video"))
    parser.add_argument("--output", type=Path, default=Path("reports/generated/static_full"))
    parser.add_argument("--encoder", choices=["h264_nvenc", "libx264"], default="h264_nvenc")
    args = parser.parse_args()
    cv2.setNumThreads(1)
    args.output.mkdir(parents=True, exist_ok=True)
    run = read_json(args.results / "run.json")
    manifest = read_json(run["mask_file"])
    if manifest["config"].get("masking_mode") != "continuous":
        parser.error("Full-video rendering requires a shared continuous masking schedule")
    if sha256_file(run["mask_file"]) != run["mask_sha256"]:
        raise ValueError("The mask manifest changed after the benchmark")
    for path, digest in run["source_sha256"].items():
        if sha256_file(path) != digest:
            raise ValueError(f"Benchmark source changed: {path}")
    predictions_by_video = defaultdict(list)
    for row in read_csv(args.results / "predictions.csv"):
        predictions_by_video[row["video_id"]].append(row)
    masks_by_video = defaultdict(list)
    for mask in manifest["masks"]:
        if mask["series_id"].startswith("object_pixels/"):
            masks_by_video[mask["series_id"].split("/")[1]].append(mask)
    summaries, timelines = [], []
    for video in sorted(masks_by_video):
        summary, timeline = render(video, masks_by_video[video], predictions_by_video[video],
                                   args.data_root, args.output, args.encoder)
        summaries.append(summary)
        timelines.append(timeline)
    write_json(args.output / "full_video_manifest.json", summaries)

    fig, axes = plt.subplots(len(timelines), 1, figsize=(12, 3 * len(timelines)), squeeze=False)
    for axis, timeline in zip(axes[:, 0], timelines):
        axis.plot([r["timestamp_s"] for r in timeline], [r["reference_cars"] for r in timeline],
                  label="Automobili di riferimento", alpha=0.65)
        axis.plot([r["timestamp_s"] for r in timeline], [r["hidden_cars"] for r in timeline],
                  label="Osservazioni nascoste e ricostruite", alpha=0.85)
        axis.set(title=timeline[0]["video_id"], xlabel="Tempo dall'inizio (s)", ylabel="Numero di automobili")
        axis.legend()
        axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(args.output / "coverage_timeline.png", dpi=150)
    plt.close(fig)

    metrics = read_csv(args.results / "summary.csv")
    fig, axis = plt.subplots(figsize=(8, 4))
    for method in METHODS:
        rows = sorted((r for r in metrics if r["method"] == method and r["micro_ade"]),
                      key=lambda r: int(r["gap_size"]))
        axis.plot([int(r["gap_size"]) for r in rows], [float(r["micro_ade"]) for r in rows],
                  "o-", color=PLOT_COLORS[method], label=method)
    axis.set(title="Automobili, telecamera fissa, mascheramento su tutto il filmato",
             xlabel="Lunghezza del gap (frame)", ylabel="ADE (pixel)")
    axis.legend()
    axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(args.output / "error_vs_gap.png", dpi=150)
    plt.close(fig)

    lines = ["# Automobili con telecamera fissa: video completi", "",
             f"- Maschere: {run['mask_count']}; valutazioni: {run['evaluations']}; fallimenti: {run['failed_evaluations']}.",
             "- Tutti i frame originali sono elaborati e visualizzati; nessun limite alle ripetizioni dei gap per traccia.",
             "- Gap di 3, 6, 12 e 24 frame lungo ogni tratto continuo utilizzabile; quattro osservazioni visibili tra gap.",
             "- Nessun punto nascosto in un gap è usato come supporto in un altro gap della stessa traccia.",
             "- Le box rosse sono riferimenti YOLO/ByteTrack nascosti, non bounding box ricostruite né annotazioni manuali.",
             "- Coordinate in pixel. I link geografici degli autori localizzano la scena, non ogni automobile.",
             "- Valutazione descrittiva post-tracking; le identità non sono ancora verificate manualmente.",
             "", "## Filmati e copertura", ""]
    for item in summaries:
        lines.extend([
            f"### {item['video_id']}", "",
            f"- Frame esportati: **{item['encoded_frames']}/{item['source_frames']}**.",
            f"- Frame con almeno una ricostruzione: **{item['frames_with_reconstruction']}**; "
            f"dal frame {item['first_reconstructed_frame']} al frame {item['last_reconstructed_frame']}.",
            f"- Tracce ricostruite: {item['reconstructed_tracks']}; osservazioni nascoste: {item['hidden_car_observations']}.",
            f"- [Apri il video completo]({Path(item['video']).name}).", "",
        ])
    lines += ["## Errori di posizione", "", "| Metodo | Gap | ADE (px) | RMS (px) | Copertura |",
              "|---|---:|---:|---:|---:|"]
    for row in metrics:
        ade = f"{float(row['micro_ade']):.4f}" if row["micro_ade"] else "n/a"
        rms = f"{float(row['micro_rms_position']):.4f}" if row["micro_rms_position"] else "n/a"
        lines.append(f"| {row['method']} | {row['gap_size']} | {ade} | {rms} | {float(row['coverage']):.0%} |")
    lines += ["", "![Copertura temporale](coverage_timeline.png)", "", "![Errori](error_vs_gap.png)", "",
              "I campioni iniziali/finali e gli intervalli senza riferimenti o supporto sufficiente rimangono osservati. "
              "Non sono presentati come ricostruzioni. La copertura numerica dei campioni mascherati è distinta dalla copertura temporale del video."]
    (args.output / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print(f"Complete video report: {args.output}", flush=True)


if __name__ == "__main__":
    main()
