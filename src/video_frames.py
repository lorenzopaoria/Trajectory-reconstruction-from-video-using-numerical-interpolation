"""Read a frame manifest from individual PNGs or one complete source video."""

import cv2


def iter_frames(rows):
    if not rows:
        return
    source = rows[0].get("source_video")
    if source:
        capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            raise ValueError(f"Cannot open {source}")
        try:
            for index, row in enumerate(rows):
                if int(row["frame"]) != index or row.get("source_video") != source:
                    raise ValueError("Video manifest must describe all frames in order")
                ok, image = capture.read()
                if not ok:
                    raise ValueError(f"Missing decoded frame {index}")
                yield row, image
            ok, _ = capture.read()
            if ok:
                raise ValueError("Source video contains frames absent from the manifest")
        finally:
            capture.release()
    else:
        for row in rows:
            image = cv2.imread(row["image_path"])
            if image is None:
                raise ValueError(f"Unreadable frame: {row['image_path']}")
            yield row, image
