"""YOLO11n + ByteTrack on original frames; save one reusable pseudo-reference."""

import argparse
import importlib.metadata
import os
from pathlib import Path
import platform
import time

from .common import read_csv, sha256_file, write_csv, write_json

FIELDS = [
    "video_id", "frame", "timestamp_s", "track_id", "class_id", "class_name",
    "confidence", "x_min", "y_min", "x_max", "y_max", "x", "y", "w", "h",
    "area", "observed",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data/urbantracker"))
    parser.add_argument("--model", type=Path, default=Path("models/yolo11n.pt"))
    parser.add_argument("--tracker", type=Path, default=Path("configs/bytetrack.yaml"))
    parser.add_argument("--device", default="auto")
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--conf", type=float, default=0.10)
    parser.add_argument("--classes", nargs="+", type=int, default=[2])
    parser.add_argument("--sequences", nargs="+", help="Only these prepared sequence IDs")
    parser.add_argument("--half", action="store_true", help="FP16 inference on CUDA")
    parser.add_argument("--batch", type=int, default=1, help="Video inference batch size")
    args = parser.parse_args()

    config_directory = Path(".cache/ultralytics").resolve()
    config_directory.mkdir(parents=True, exist_ok=True)
    os.environ["YOLO_CONFIG_DIR"] = str(config_directory)
    os.environ["YOLO_AUTOINSTALL"] = "false"
    import cv2
    import torch
    from ultralytics import YOLO
    from .video_frames import iter_frames

    torch.set_num_threads(2)
    cv2.setNumThreads(1)

    device = ("0" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
    if device != "cpu" and not torch.cuda.is_available():
        parser.error("CUDA was requested but is not available")
    if args.batch < 1:
        parser.error("Batch size must be positive")
    print(f"Requested device: {device}; batch={args.batch}; precision={'FP16' if args.half else 'FP32'}", flush=True)
    if device != "cpu":
        print(f"GPU: {torch.cuda.get_device_name(int(device))}", flush=True)
    manifests = sorted((args.data_root / "prepared").glob("*/frames.csv"))
    if args.sequences:
        manifests = [path for path in manifests if path.parent.name in args.sequences]
        missing = set(args.sequences) - {path.parent.name for path in manifests}
        if missing:
            parser.error(f"Sequences not prepared: {sorted(missing)}")
    if not manifests:
        parser.error("No prepared frames. Run the dataset preparation command first.")
    args.model.parent.mkdir(parents=True, exist_ok=True)
    for manifest in manifests:
        sequence = manifest.parent.name
        frames = read_csv(manifest)
        # New model/predictor means a fresh tracker for each video.
        model = YOLO(str(args.model))
        rows = []
        started = time.perf_counter()
        def results():
            options = dict(persist=True, tracker=str(args.tracker), device=device,
                           imgsz=args.imgsz, conf=args.conf, iou=0.7, classes=args.classes,
                           verbose=False, save=False, seed=0, deterministic=True,
                           quantize=16 if args.half else 32, batch=args.batch, vid_stride=1)
            if frames[0].get("source_video"):
                yield from model.track(frames[0]["source_video"], stream=True, **options)
            else:
                for _, image in iter_frames(frames):
                    yield model.track(image, **options)[0]

        processed = 0
        for index, result in enumerate(results()):
            if index >= len(frames):
                raise ValueError("Tracker decoded more frames than the manifest")
            frame = frames[index]
            processed += 1
            if index == 0:
                backend = model.predictor.model
                print(f"Actual model device: {backend.device}; FP16={backend.fp16}; first-frame timings={result.speed}", flush=True)
            boxes = result.boxes
            if boxes is not None and boxes.id is not None:
                for bounds, track_id, cls, score in zip(
                    boxes.xyxy.cpu().numpy(), boxes.id.int().cpu().tolist(),
                    boxes.cls.int().cpu().tolist(), boxes.conf.cpu().tolist(),
                ):
                    x1, y1, x2, y2 = map(float, bounds)
                    rows.append({
                        "video_id": sequence, "frame": int(frame["frame"]),
                        "timestamp_s": float(frame["timestamp_s"]), "track_id": track_id,
                        "class_id": cls, "class_name": model.names[cls], "confidence": score,
                        "x_min": x1, "y_min": y1, "x_max": x2, "y_max": y2,
                        "x": (x1 + x2) / 2, "y": y2, "w": x2 - x1, "h": y2 - y1,
                        "area": (x2 - x1) * (y2 - y1), "observed": True,
                    })
            if (index + 1) % 250 == 0 or index + 1 == len(frames):
                rate = (index + 1) / (time.perf_counter() - started)
                print(f"{sequence}: {index + 1}/{len(frames)} frames, {len(rows)} boxes, {rate:.1f} fps", flush=True)
        output = args.data_root / "tracks" / sequence
        if processed != len(frames):
            raise ValueError(f"Tracker decoded {processed} frames; expected {len(frames)}")
        csv_path = output / "tracks.csv"
        write_csv(csv_path, rows, FIELDS)
        write_json(output / "tracking_metadata.json", {
            "sequence": sequence, "processed_frames": len(frames), "observations": len(rows),
            "track_ids": len({r["track_id"] for r in rows}),
            "reference_type": "matched YOLO/ByteTrack output boxes; not manual object ground truth",
            "protocol": "full-sequence tracking before masking; conditional interpolation",
            "model": str(args.model), "model_sha256": sha256_file(args.model),
            "tracker": str(args.tracker), "tracker_sha256": sha256_file(args.tracker),
            "frames_sha256": sha256_file(manifest), "tracks_sha256": sha256_file(csv_path),
            "device": device, "imgsz": args.imgsz, "conf": args.conf,
            "half": args.half,
            "batch": args.batch, "vid_stride": 1,
            "actual_model_device": str(model.predictor.model.device),
            "iou": 0.7, "classes": args.classes, "seed": 0,
            "elapsed_s": time.perf_counter() - started,
            "python": platform.python_version(),
            "versions": {package: importlib.metadata.version(package) for package in (
                "ultralytics", "torch", "torchvision", "numpy", "scipy", "opencv-python", "lap",
            )},
        })


if __name__ == "__main__":
    main()
