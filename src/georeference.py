"""Adapter to GeminiPort schema-v2 ground calibrations; explicit East/North order."""

import importlib
import os
from pathlib import Path
import sys

import numpy as np

from .common import read_json, sha256_file

PROJECT = Path(__file__).resolve().parents[1]


def project_path(value):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (PROJECT / path).resolve()


def settings(path="configs/georeferencing.json"):
    config = read_json(project_path(path))
    config["geminiport_root"] = str(Path(os.environ.get("GEMINIPORT_ROOT", config["geminiport_root"])).expanduser().resolve())
    config["calibration_directory"] = str(project_path(config["calibration_directory"]))
    return config


def shared_api(config):
    root = Path(config["geminiport_root"])
    if (root / "ground_geometry" / "modules" / "calibration.py").is_file():
        calibration_module = "ground_geometry.modules.calibration"
        geometry_module = "ground_geometry.modules.homography"
    elif ((root / "trafficdetGUI" / "modules" / "ground_projection.py").is_file()
          and (root / "ground_geometry" / "homography.py").is_file()):
        calibration_module = "trafficdetGUI.modules.ground_projection"
        geometry_module = "ground_geometry.homography"
    else:
        raise FileNotFoundError("GeminiPort ground_geometry not found; set GEMINIPORT_ROOT or configs/georeferencing.json")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    calibration = importlib.import_module(calibration_module)
    geometry = importlib.import_module(geometry_module)
    if not Path(calibration.__file__).resolve().is_relative_to(root):
        raise RuntimeError("A different GeminiPort calibration package is already imported")
    return calibration, geometry


class GroundCalibration:
    """Reuse the shared validator/projector without bypassing its valid polygon."""

    def __init__(self, config, video_id, width, height):
        self.api, self.geometry = shared_api(config)
        scene = config["scenes"][video_id]
        self.path = Path(config["calibration_directory"]) / (scene["camera_id"] + ".json")
        if not self.path.is_file():
            raise FileNotFoundError(f"Calibrazione mancante: {self.path}. Eseguire python3 -m src.calibrate_ground e Pubblica.")
        self.calibration_sha256 = sha256_file(self.path)
        self.projector = self.api.GroundProjector.load(self.path)
        if sha256_file(self.path) != self.calibration_sha256:
            raise ValueError("Calibration changed while loading; retry after saving has finished")
        self.document = self.projector.document
        if self.document["camera_id"] != scene["camera_id"]:
            raise ValueError("Calibration Camera ID does not match this scene")
        self.width, self.height = int(width), int(height)
        self.source = str(project_path(scene["source"]))
        # Saved tracking uses original pixels, without crop/unwrap/undistortion.
        # A differently preprocessed calibration is intentionally incompatible.
        self.preprocessing = None
        compatible = self.projector.compatibility(self.width, self.height, source=self.source,
                                                   preprocessing=self.preprocessing)
        if not compatible.compatible:
            raise ValueError(f"Calibrazione incompatibile con i pixel del tracking: {compatible.to_dict()}")

    def project(self, pixel):
        result = self.projector.project(pixel, self.width, self.height, source=self.source,
                                        preprocessing=self.preprocessing)
        return {"east_m": result.east_m, "north_m": result.north_m,
                "latitude_deg": result.latitude, "longitude_deg": result.longitude}

    def world_coordinates(self, east_north):
        points = np.atleast_2d(np.asarray(east_north, dtype=float))
        # GeminiPort's local coordinate order is North/East, not East/North.
        return self.geometry.local_to_wgs84(points[:, [1, 0]], self.projector.origin)

    def local_coordinates(self, latitude_longitude):
        local_ne, _ = self.geometry.wgs84_to_local(latitude_longitude, self.projector.origin)
        return local_ne[:, [1, 0]]


def calibration_status(config, data_root=None):
    data_root = project_path(data_root or "data/urbantracker")
    records = []
    for video, scene in config["scenes"].items():
        path = Path(config["calibration_directory"]) / (scene["camera_id"] + ".json")
        record = {"video_id": video, "camera_id": scene["camera_id"], "path": str(path),
                  "status": "missing", "message": "Da calibrare manualmente"}
        if path.exists():
            try:
                document = read_json(path)
                if document.get("status") == "draft":
                    record.update(status="draft", message="Bozza: completare i punti e premere Pubblica")
                else:
                    meta = read_json(data_root / "prepared" / video / "metadata.json")
                    model = GroundCalibration(config, video, meta["width"], meta["height"])
                    record.update(status="ready", message="Calibrazione valida e compatibile",
                                  control_points=len(model.document["image_points"]),
                                  fit_rms_m=model.document["rms_m"])
            except (ValueError, OSError, RuntimeError) as error:
                record.update(status="invalid", message=str(error))
        records.append(record)
    return records
