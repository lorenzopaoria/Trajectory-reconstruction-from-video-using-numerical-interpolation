"""Short car-passage clips: bright-red reference, one interpolator per panel."""

import argparse
from collections import defaultdict
import csv
import itertools
from pathlib import Path
import subprocess

import cv2
import numpy as np

from .common import read_csv, read_json, sha256_file, write_json
from .methods import METHODS, REFERENCE_BGR

TILE_W, TILE_H, BAND_H = 640, 330, 90
IMAGE_Y, IMAGE_H = 38, 270


def motion_metrics(times, positions, widths):
    """Robust reference-only visual selection; these smoothed data never reach fit."""
    block = max(3, round(0.25 / np.median(np.diff(times))))
    smooth = np.array([np.median(positions[i:i + block], axis=0) for i in range(0, len(times), block)])
    sample_times = np.array([np.median(times[i:i + block]) for i in range(0, len(times), block)])
    steps = np.linalg.norm(np.diff(smooth, axis=0), axis=1)
    displacement = float(np.linalg.norm(smooth[-1] - smooth[0]))
    median_width = float(np.median(widths))
    speed_threshold = max(3.0, 0.08 * median_width)
    return {
        "displacement_px": displacement,
        "displacement_widths": displacement / median_width,
        "moving_fraction": float(np.mean(steps / np.diff(sample_times) >= speed_threshold)),
        "directional_coherence": displacement / float(steps.sum()) if steps.sum() else 0.0,
        "maximum_frame_jump_px": float(np.linalg.norm(np.diff(positions, axis=0), axis=1).max()),
        "median_width_px": median_width,
    }


def candidates_for_track(video, track, rows, hidden_frames, config, image_size):
    frames = np.array([int(row["frame"]) for row in rows])
    times = np.array([float(row["timestamp_s"]) for row in rows])
    edges = np.r_[0, np.flatnonzero(np.diff(frames) != 1) + 1, len(frames)]
    candidates = []
    for begin, end in zip(edges[:-1], edges[1:]):
        if end - begin < 3:
            continue
        dt = float(np.median(np.diff(times[begin:end])))
        minimum = int(np.ceil(config["minimum_seconds"] / dt))
        target = int(round(config["target_seconds"] / dt))
        stride = max(1, int(round(config["candidate_stride_seconds"] / dt)))
        for first in range(int(begin), int(end) - minimum + 1, stride):
            stop = min(first + target, int(end))
            selected = rows[first:stop]
            masked_count = sum(int(row["frame"]) in hidden_frames for row in selected)
            if masked_count < config["minimum_masked_samples"]:
                continue
            boxes = np.array([[float(row[k]) for k in ("x_min", "y_min", "x_max", "y_max")] for row in selected])
            widths, heights = boxes[:, 2] - boxes[:, 0], boxes[:, 3] - boxes[:, 1]
            if float(np.median(heights)) < config["minimum_median_height_px"]:
                continue
            positions = np.array([[float(row["x"]), float(row["y"])] for row in selected])
            motion = motion_metrics(times[first:stop], positions, widths)
            if (motion["displacement_px"] < config["minimum_displacement_px"]
                    or motion["displacement_widths"] < config["minimum_displacement_widths"]
                    or motion["moving_fraction"] < config["minimum_moving_fraction"]
                    or motion["directional_coherence"] < config["minimum_directional_coherence"]
                    or motion["maximum_frame_jump_px"] > max(30.0, 0.75 * motion["median_width_px"])):
                continue
            low, high = boxes[:, :2].min(axis=0), boxes[:, 2:].max(axis=0)
            margin = max(24.0, 0.15 * float(np.max(high - low)))
            crop = [max(0, int(np.floor(low[0] - margin))), max(0, int(np.floor(low[1] - margin))),
                    min(image_size[0], int(np.ceil(high[0] + margin))), min(image_size[1], int(np.ceil(high[1] + margin)))]
            candidates.append({
                "video_id": video, "track_id": track,
                "start_frame": int(frames[first]), "end_frame": int(frames[stop - 1]),
                "start_s": float(times[first]), "end_s": float(times[stop - 1]),
                "center_s": float((times[first] + times[stop - 1]) / 2),
                "frame_count": stop - first, "masked_samples": masked_count, "crop_xyxy": crop,
                "median_height_px": float(np.median(heights)), **motion,
            })
    return candidates


def choose_passages(root, manifest, config):
    hidden = defaultdict(set)
    for mask in manifest["masks"]:
        if mask["series_id"].startswith("object_pixels/"):
            _, video, track = mask["series_id"].split("/")
            hidden[(video, track)].update(mask["hidden_frames"])
    events, counts = [], {}
    for video in sorted({key[0] for key in hidden}):
        metadata = read_json(root / "prepared" / video / "metadata.json")
        groups = defaultdict(list)
        with (root / "tracks" / video / "tracks.csv").open(newline="") as source:
            for row in csv.DictReader(source):
                if (video, row["track_id"]) in hidden:
                    groups[row["track_id"]].append(row)
        candidates = []
        for track, rows in sorted(groups.items()):
            rows.sort(key=lambda row: int(row["frame"]))
            candidates.extend(candidates_for_track(video, track, rows, hidden[(video, track)], config,
                                                  (metadata["width"], metadata["height"])))
        counts[video] = {"eligible_candidate_windows": len(candidates), "candidate_tracks": len({r["track_id"] for r in candidates})}
        # Spread across the source timeline, one passage per ID. No interpolation
        # predictions or error scores enter selection or crop computation.
        chosen_tracks = set()
        duration = metadata["duration_between_first_last_s"]
        centers = (np.arange(config["clips_per_video"]) + 0.5) * duration / config["clips_per_video"]
        for center in centers:
            available = [c for c in candidates if c["track_id"] not in chosen_tracks]
            if not available:
                break
            selected = min(available, key=lambda c: (abs(c["center_s"] - center), -c["median_height_px"], c["track_id"]))
            selected = dict(selected)
            selected["clip_id"] = f"{video}_car{selected['track_id']}_f{selected['start_frame']:05d}"
            selected["filename"] = selected["clip_id"] + ".mp4"
            events.append(selected)
            chosen_tracks.add(selected["track_id"])
    return sorted(events, key=lambda c: (c["video_id"], c["start_frame"])), counts


def clip_frames(rows, start, end):
    """Decode only the chosen interval, preserving zero-based source frame IDs."""
    selected = rows[start:end + 1]
    video = selected[0].get("source_video")
    if video:
        capture = cv2.VideoCapture(video)
        try:
            if not capture.isOpened() or not capture.set(cv2.CAP_PROP_POS_FRAMES, start):
                raise ValueError("Cannot seek source video")
            if round(capture.get(cv2.CAP_PROP_POS_FRAMES)) != start:
                raise ValueError("Video seek did not reach the requested frame")
            for row in selected:
                ok, image = capture.read()
                if not ok or round(capture.get(cv2.CAP_PROP_POS_FRAMES)) != int(row["frame"]) + 1:
                    raise ValueError("Unexpected decoded frame position")
                yield row, image
        finally:
            capture.release()
    else:
        for row in selected:
            image = cv2.imread(row["image_path"])
            if image is None:
                raise ValueError(f"Missing frame {row['frame']}")
            yield row, image


def path_line(image, points, color, thickness, outline=True):
    valid = np.isfinite(points).all(axis=1)
    edges = np.r_[0, np.flatnonzero(np.diff(valid.astype(int))) + 1, len(points)]
    for first, end in zip(edges[:-1], edges[1:]):
        if end - first < 2 or not valid[first]:
            continue
        segment = np.rint(points[first:end]).astype(np.int32)
        if outline:
            cv2.polylines(image, [segment], False, (10, 10, 10), thickness + 2, cv2.LINE_AA)
        cv2.polylines(image, [segment], False, color, thickness, cv2.LINE_AA)


def render_clip(event, frame_rows, reference, predictions, hidden, gap_sizes, methods, output):
    x1, y1, x2, y2 = event["crop_xyxy"]
    factor = min((TILE_W - 12) / (x2 - x1), (IMAGE_H - 8) / (y2 - y1))
    width, height = round((x2 - x1) * factor), round((y2 - y1) * factor)
    offset = np.array([(TILE_W - width) // 2, IMAGE_Y + (IMAGE_H - height) // 2])
    frames = np.arange(event["start_frame"], event["end_frame"] + 1)
    points = np.array([[float(reference[f]["x"]), float(reference[f]["y"])] for f in frames])
    transform = lambda p: (p - np.array([x1, y1])) * factor + offset
    red_path = transform(points)
    estimates = {}
    for method in methods:
        curve = points.copy()
        for i, frame in enumerate(frames):
            if frame in hidden:
                curve[i] = predictions.get((frame, method), (np.nan, np.nan))
        estimates[method] = (curve, transform(curve))
    fps = (len(frames) - 1) / (float(frame_rows[frames[-1]]["timestamp_s"]) - float(frame_rows[frames[0]]["timestamp_s"]))
    columns = 3
    panel_rows = int(np.ceil((len(methods) + 1) / columns))
    video_width, video_height = TILE_W * columns, BAND_H + TILE_H * panel_rows
    destination = output / event["filename"]
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
               "-pixel_format", "bgr24", "-video_size", f"{video_width}x{video_height}",
               "-framerate", str(fps), "-i", "pipe:0", "-c:v", "h264_nvenc", "-preset", "p4",
               "-rc", "vbr", "-cq", "20", "-b:v", "0", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(destination)]
    encoded = 0
    with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
        try:
            for i, (frame_row, image) in enumerate(clip_frames(frame_rows, int(frames[0]), int(frames[-1]))):
                frame = int(frame_row["frame"])
                base = np.full((TILE_H, TILE_W, 3), 22, dtype=np.uint8)
                base[offset[1]:offset[1] + height, offset[0]:offset[0] + width] = cv2.resize(image[y1:y2, x1:x2], (width, height))
                canvas = np.full((video_height, video_width, 3), 15, dtype=np.uint8)
                cv2.putText(canvas, f"{event['video_id']} | AUTO {event['track_id']} | t={float(frame_row['timestamp_s']):.2f}s | frame {frame}",
                            (20, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (245, 245, 245), 2, cv2.LINE_AA)
                cv2.putText(canvas, "ROSSO ACCESO: riferimento YOLO/ByteTrack | COLORI: interpolatori | stessi nodi e gap", (20, 56),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.62, (220, 220, 220), 1, cv2.LINE_AA)
                cv2.putText(canvas, "Vandermonde, Lagrange e Newton: stesso polinomio, algoritmi diversi. Zoom fisso; errori in pixel originali.",
                            (20, 79), cv2.FONT_HERSHEY_SIMPLEX, 0.53, (190, 190, 190), 1, cv2.LINE_AA)
                for panel, method in enumerate([None] + list(methods)):
                    tile = base.copy()
                    path_line(tile, red_path[:i + 1], REFERENCE_BGR, 6)
                    ref_point = tuple(np.rint(red_path[i]).astype(int))
                    ref = reference[frame]
                    box = transform(np.array([[float(ref["x_min"]), float(ref["y_min"])],
                                              [float(ref["x_max"]), float(ref["y_max"])]]))
                    cv2.rectangle(tile, tuple(np.rint(box[0]).astype(int)), tuple(np.rint(box[1]).astype(int)), (240, 240, 240), 1)
                    cv2.circle(tile, ref_point, 5, REFERENCE_BGR, 2 if frame in hidden else -1, cv2.LINE_AA)
                    title, color = ("YOLO/ByteTrack - riferimento", REFERENCE_BGR) if method is None else (METHODS[method]["label"], METHODS[method]["bgr"])
                    status = "Campione nascosto (solo per confronto)" if frame in hidden else "Osservazione disponibile"
                    if method is not None:
                        curve, display = estimates[method]
                        path_line(tile, display[:i + 1], color, 2)
                        if frame in hidden:
                            if np.isfinite(curve[i]).all():
                                error = float(np.linalg.norm(curve[i] - points[i]))
                                outside = not (x1 <= curve[i, 0] <= x2 and y1 <= curve[i, 1] <= y2)
                                status = f"Gap {gap_sizes[frame]} frame | errore {error:.3f} px" + (" | FUORI VISTA" if outside else "")
                                if not outside:
                                    cv2.circle(tile, tuple(np.rint(display[i]).astype(int)), 5, color, -1, cv2.LINE_AA)
                            else:
                                status = "RICOSTRUZIONE FALLITA"
                    # Redraw text bands after paths: off-crop estimates cannot overwrite labels.
                    cv2.rectangle(tile, (0, 0), (TILE_W, IMAGE_Y - 1), (22, 22, 22), -1)
                    cv2.rectangle(tile, (0, TILE_H - 22), (TILE_W, TILE_H), (22, 22, 22), -1)
                    cv2.putText(tile, title, (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.64, color, 2, cv2.LINE_AA)
                    cv2.putText(tile, status, (8, TILE_H - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (235, 235, 235), 1, cv2.LINE_AA)
                    top, left = BAND_H + (panel // columns) * TILE_H, (panel % columns) * TILE_W
                    canvas[top:top + TILE_H, left:left + TILE_W] = tile
                    cv2.rectangle(canvas, (left, top), (left + TILE_W - 1, top + TILE_H - 1), (80, 80, 80), 1)
                if i == len(frames) // 2:
                    cv2.imwrite(str(output / (event["clip_id"] + ".jpg")), canvas)
                encoder.stdin.write(canvas.tobytes())
                encoded += 1
        finally:
            encoder.stdin.close()
        if encoder.wait() != 0:
            raise RuntimeError("NVENC encoding failed")
    if encoded != event["frame_count"]:
        raise ValueError("Clip frame count mismatch")
    return dict(event, encoded_frames=encoded, fps=fps, duration_s=encoded / fps,
                encoder="h264_nvenc", methods=list(methods), reference_color="#FF0000",
                video_sha256=sha256_file(destination), width=video_width, height=video_height)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data/urbantracker"))
    parser.add_argument("--results", type=Path, default=Path("data/urbantracker/results/course"))
    parser.add_argument("--config", type=Path, default=Path("configs/clips.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/generated/course/clips"))
    parser.add_argument("--select-only", action="store_true")
    args = parser.parse_args()
    cv2.setNumThreads(1)
    args.output.mkdir(parents=True, exist_ok=True)
    run = read_json(args.results / "run.json")
    manifest = read_json(run["mask_file"])
    if sha256_file(run["mask_file"]) != run["mask_sha256"]:
        raise ValueError("Masks changed since the experiment")
    for path, digest in run["source_sha256"].items():
        if sha256_file(path) != digest:
            raise ValueError(f"Reference data changed: {path}")
    config = read_json(args.config)
    if config["encoder"] != "h264_nvenc":
        parser.error("This clip configuration requires GPU encoding with h264_nvenc")
    events, counts = choose_passages(args.data_root, manifest, config)
    if not events:
        raise ValueError("No moving passages satisfy the clip criteria")
    write_json(args.output / "selection.json", {"config": config, "candidates": counts, "clips": events,
               "selection_policy": "reference motion, geometry and time coverage only; independent of interpolation errors"})
    print(f"Selected {len(events)} passages; candidate counts: {counts}", flush=True)
    if args.select_only:
        return
    by_track = defaultdict(list)
    for event in events:
        by_track[(event["video_id"], event["track_id"])].append(event)
    predictions = defaultdict(dict)
    with (args.results / "predictions.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row["video_id"], row["track_id"])
            frame = int(row["frame"])
            for event in by_track.get(key, []):
                if event["start_frame"] <= frame <= event["end_frame"]:
                    predictions[event["clip_id"]][(frame, row["method"])] = (float(row["predicted_x"]), float(row["predicted_y"]))
    hidden, gap_sizes = defaultdict(set), defaultdict(dict)
    for mask in manifest["masks"]:
        if not mask["series_id"].startswith("object_pixels/"):
            continue
        _, video, track = mask["series_id"].split("/")
        if (video, track) in by_track:
            hidden[(video, track)].update(mask["hidden_frames"])
            gap_sizes[(video, track)].update({frame: mask["gap_size"] for frame in mask["hidden_frames"]})
    rendered = []
    for video, grouped in itertools.groupby(events, key=lambda c: c["video_id"]):
        frame_rows = read_csv(args.data_root / "prepared" / video / "frames.csv")
        references = defaultdict(dict)
        with (args.data_root / "tracks" / video / "tracks.csv").open(newline="") as stream:
            for row in csv.DictReader(stream):
                if (video, row["track_id"]) in by_track:
                    references[row["track_id"]][int(row["frame"])] = row
        for event in grouped:
            key = (video, event["track_id"])
            rendered.append(render_clip(event, frame_rows, references[event["track_id"]], predictions[event["clip_id"]],
                                        hidden[key], gap_sizes[key], run["config"]["methods"], args.output))
            write_json(args.output / "manifest.json", rendered)
            print(f"NVENC: {event['filename']} ({event['frame_count']} frames)", flush=True)
    lines = ["# Clip dei passaggi delle automobili", "",
             "Rosso acceso: riferimento YOLO/ByteTrack. Ogni riquadro confronta lo stesso passaggio con un metodo diverso.",
             "Le clip sono selezionate per movimento e distribuzione temporale, non per errore ottenuto.",
             "Le osservazioni rosse nei gap sono disponibili solo al valutatore. S2 e razionale FH sono etichettate come estensioni.", ""]
    for clip in rendered:
        lines += [f"## {clip['video_id']} — auto {clip['track_id']}", "",
                  f"[Apri clip]({clip['filename']}) · {clip['duration_s']:.2f} s · frame {clip['start_frame']}–{clip['end_frame']}", "",
                  f"![Anteprima]({clip['clip_id']}.jpg)", ""]
    (args.output / "INDEX.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
