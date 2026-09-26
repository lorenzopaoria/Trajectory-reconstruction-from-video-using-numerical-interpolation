"""Launch the existing GeminiPort calibration editor for the project's original videos."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .common import write_json
from .georeference import PROJECT, calibration_status, project_path, settings


def editor_command(config, scenes, python):
    root = Path(config["geminiport_root"])
    launcher = root / "ground_geometry" / "run_calibration.py"
    if not launcher.is_file():
        if (root / "trafficdetGUI" / "modules" / "calibration_gui.py").is_file():
            return [str(python), "-m", "src.calibrate_ground", "--legacy-editor", "--scenes", *scenes]
        raise FileNotFoundError(f"Calibration editor not found: {launcher}")
    command = [str(python), str(launcher), "--calibration-dir", config["calibration_directory"]]
    for video in scenes:
        scene = config["scenes"][video]
        source = project_path(scene["source"])
        if not source.is_file():
            raise FileNotFoundError(f"Missing source video: {source}")
        command.extend(["--source", str(source), "--camera-id", scene["camera_id"]])
    return command


def legacy_editor(config, scenes):
    """Use GeminiPort's schema-v2 dialog when the standalone editor is unavailable."""
    import importlib
    import cv2
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .georeference import shared_api
    shared_api(config)
    module = importlib.import_module("trafficdetGUI.modules.calibration_gui")
    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationName("Calibrazione traiettorie")
    for video in scenes:
        scene = config["scenes"][video]
        source = str(project_path(scene["source"]))
        path = Path(config["calibration_directory"]) / (scene["camera_id"] + ".json")
        capture = cv2.VideoCapture(source)
        try:
            capture.set(cv2.CAP_PROP_POS_MSEC, 1500)
            ok, frame = capture.read()
        finally:
            capture.release()
        if not ok:
            raise ValueError(f"Cannot read calibration frame: {source}")
        center = scene.get("scene_center_lat_lon", [])
        QMessageBox.information(None, scene["camera_id"],
            f"Centro approssimativo della scena: {center}\n"
            "Usa il riferimento mappa indicato in docs/calibrazione.md per trovare le coordinate dei punti.\n"
            "Questo dialogo salva nello stesso schema v2 e accetta coordinate manuali.")
        module.open_calibration_dialog(frame, camera_id=scene["camera_id"], source=source,
            calibration_path=path, preprocessing={}, camera_location=None, inlier_threshold_m=1.0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/georeferencing.json")
    parser.add_argument("--scenes", nargs="+")
    parser.add_argument("--python", default=sys.executable, help="Interpreter with NumPy, OpenCV and PySide6")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--print-command", action="store_true")
    parser.add_argument("--detach", action="store_true", help="Leave the editor open on the desktop")
    parser.add_argument("--legacy-editor", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    config = settings(args.config)
    if args.status:
        print(json.dumps(calibration_status(config), indent=2, ensure_ascii=False))
        return
    scenes = args.scenes or list(config["scenes"])
    if set(scenes) - set(config["scenes"]):
        parser.error("Unknown scene")
    if args.legacy_editor:
        Path(config["calibration_directory"]).mkdir(parents=True, exist_ok=True)
        legacy_editor(config, scenes)
        return
    command = editor_command(config, scenes, args.python)
    if "--legacy-editor" in command:
        command.extend(["--config", str(project_path(args.config))])
    if args.print_command:
        import shlex
        print(shlex.join(command))
        return
    Path(config["calibration_directory"]).mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment["GEMINIPORT_CALIBRATION_DIR"] = config["calibration_directory"]
    # These sources are files; cap decoder worker threads for responsive startup.
    environment.setdefault("OPENCV_FFMPEG_THREADS", "2")
    if args.detach:
        log_path = PROJECT / ".cache" / "calibration_editor.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w") as log:
            process = subprocess.Popen(command, cwd=PROJECT, env=environment,
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        time.sleep(3)
        code = process.poll()
        if code is not None and code != 0:
            raise RuntimeError(f"Editor exited with code {code}; see {log_path}")
        write_json(PROJECT / ".cache" / "calibration_editor.json", {"pid": process.pid, "scenes": scenes,
                   "log": str(log_path), "calibration_directory": config["calibration_directory"]})
        print(f"Editor avviato, PID {process.pid}. Selezionare i punti e premere Pubblica.")
        print(f"Calibrazioni: {config['calibration_directory']}")
    else:
        subprocess.run(command, cwd=PROJECT, env=environment, check=True)


if __name__ == "__main__":
    main()
