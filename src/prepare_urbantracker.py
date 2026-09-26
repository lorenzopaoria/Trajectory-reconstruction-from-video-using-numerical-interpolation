"""Download and prepare complete fixed-camera traffic clips from Urban Tracker."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import json
from urllib.request import Request, urlopen
import zipfile

import numpy as np

from .common import read_json, sha256_file, write_csv, write_json

SOURCE = "https://www.jpjodoin.com/urbantracker/dataset.html"
BASE = "https://www.jpjodoin.com/urbantracker/dataset"
SCENES = {
    "sherbrooke": {
        "extension": "avi", "location": "Sherbrooke/Amherst intersection, Montreal",
        "geographic_link": "https://www.bing.com/maps/?v=2&cp=rkm6648w2k6d&lvl=19.27&dir=177.75&sty=o",
    },
    "rene": {
        "extension": "mov", "location": "Rene-Levesque, Montreal; view of three intersections",
        "geographic_link": "https://www.bing.com/maps/?v=2&cp=rkg7498w1ygj&lvl=19.26&dir=359.66&sty=o",
    },
}


def download(url, folder):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / url.rsplit("/", 1)[1]
    with urlopen(Request(url, method="HEAD"), timeout=60) as response:
        size = int(response.headers["Content-Length"])
    if not path.exists() or path.stat().st_size != size:
        temporary = path.with_suffix(path.suffix + ".part")
        offset = temporary.stat().st_size if temporary.exists() else 0
        if offset > size:
            raise ValueError(f"Unexpected partial file size: {temporary}")
        if offset < size:
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            with urlopen(Request(url, headers=headers), timeout=120) as response:
                if response.status == 206:
                    if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                        raise ValueError("Invalid resume response")
                else:
                    offset = 0
                with temporary.open("ab" if offset else "wb") as stream:
                    while chunk := response.read(1024 * 1024):
                        stream.write(chunk)
        if temporary.stat().st_size != size:
            raise ValueError("Incomplete download; rerun to resume")
        temporary.replace(path)
    print(f"Available: {path.name}, {size:,} bytes", flush=True)
    return path, {"url": url, "bytes": size, "sha256": sha256_file(path)}


def prepare(scene, data_root):
    info = SCENES[scene]
    raw = data_root / "raw" / scene
    video, video_source = download(f"{BASE}/{scene}/{scene}_video.{info['extension']}", raw)
    labels, labels_source = download(f"{BASE}/{scene}/{scene}_annotations.zip", raw)
    with zipfile.ZipFile(labels) as archive:
        if archive.testzip() is not None:
            raise ValueError("Corrupt annotations archive")
    source = {
        "dataset": "Urban Tracker", "scene": scene, "source_page": SOURCE,
        "citation": "Jodoin, Bilodeau, Saunier. Urban Tracker: Multiple Object Tracking in Urban Mixed Traffic. WACV 2014.",
        "license": "No explicit license identified on the dataset page; authors request citation",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": [video_source, labels_source], "camera_motion": "fixed",
        "scene_location": info["location"], "scene_geographic_link": info["geographic_link"],
        "gps_per_frame": False, "object_lat_lon": False,
        "geography_note": "Published scene-location link only; not surveyed camera coordinates or object GPS",
        "annotations": "Original Polytrack ZIP retained, not yet used in numerical evaluation",
    }
    write_json(raw / "download_manifest.json", source)

    output = data_root / "prepared" / f"urban_{scene}"
    images = output / "images"
    metadata_path = output / "metadata.json"
    if metadata_path.exists() and (output / "frames.csv").exists() and (output / "video.mp4").exists():
        existing = read_json(metadata_path)
        if (existing["source"]["files"] == source["files"]
                and existing["frames_csv_sha256"] == sha256_file(output / "frames.csv")
                and (existing.get("frame_storage") == "source_video"
                     or len(list(images.glob("*.png"))) == existing["frame_count"])):
            print(f"Already prepared: {output.name}, {existing['frame_count']} frames", flush=True)
            return

    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_packets", "-show_streams",
        "-show_entries", "packet=pts_time:stream=nb_frames,width,height,codec_name,pix_fmt",
        "-of", "json", str(video),
    ], check=True, capture_output=True, text=True)
    probe_data = json.loads(probe.stdout)
    stream = probe_data["streams"][0]
    stamps = np.sort([float(row["pts_time"]) for row in probe_data["packets"]])
    if len(stamps) != int(stream["nb_frames"]):
        raise ValueError("Expected one timestamped video packet per frame for this dataset")
    if len(stamps) < 2 or not np.isfinite(stamps).all() or np.any(np.diff(stamps) <= 0):
        raise ValueError("Invalid video presentation timestamps")
    seconds = stamps - stamps[0]
    output.mkdir(parents=True, exist_ok=True)
    dimensions = (int(stream["width"]), int(stream["height"]))
    rows = [{"video_id": output.name, "frame": index, "timestamp_s": float(seconds[index]),
             "source_pts_s": float(stamp), "image_path": "", "source_video": str(video.resolve())}
            for index, stamp in enumerate(stamps)]
    write_csv(output / "frames.csv", rows)
    fps = (len(rows) - 1) / seconds[-1]
    # Complete sequence, no clipping or subsampling; original PTS drive numerical fitting.
    encoding = ["-c:v", "copy"] if (
        stream["codec_name"] == "h264" and stream["pix_fmt"] == "yuv420p"
        and dimensions[0] % 2 == 0 and dimensions[1] % 2 == 0
    ) else ["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264",
            "-preset", "ultrafast", "-threads", "2", "-crf", "20", "-pix_fmt", "yuv420p"]
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
        "-map", "0:v:0", "-an", *encoding,
        "-fps_mode", "passthrough", "-movflags", "+faststart", str(output / "video.mp4"),
    ], check=True)
    write_json(output / "metadata.json", {
        "sequence": output.name, "frame_count": len(rows), "width": dimensions[0], "height": dimensions[1],
        "duration_between_first_last_s": float(seconds[-1]), "preview_fps": float(fps),
        "camera_motion": "fixed", "gps_subject": None, "source": source,
        "frame_storage": "source_video",
        "timestamp_policy": "original video presentation timestamps; zero-based frame index",
        "full_source_video": True, "frames_csv_sha256": sha256_file(output / "frames.csv"),
        "video_sha256": sha256_file(output / "video.mp4"),
    })
    print(f"Prepared {output.name}: ALL {len(rows)} frames, {seconds[-1]:.3f} s, {fps:.3f} fps", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenes", nargs="+", choices=SCENES, default=list(SCENES))
    parser.add_argument("--data-root", type=Path, default=Path("data/urbantracker"))
    args = parser.parse_args()
    for scene in args.scenes:
        prepare(scene, args.data_root)


if __name__ == "__main__":
    main()
