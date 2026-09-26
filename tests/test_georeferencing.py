import copy
from pathlib import Path
import tempfile
import unittest

import numpy as np

from src.common import write_csv, write_json
from src.georeference import GroundCalibration, settings, shared_api
from src.metric_benchmark import calibrated_cases
from src.project_ground import project_record, project_sequence


class GroundProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = settings()
        try:
            cls.api, cls.geometry = shared_api(cls.config)
        except FileNotFoundError as error:
            raise unittest.SkipTest(str(error))

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.directory.cleanup)
        folder = Path(self.directory.name)
        self.config = copy.deepcopy(self.config)
        self.config["calibration_directory"] = str(folder)
        self.source = str(folder / "synthetic_plane.mp4")
        self.config["scenes"] = {"synthetic": {"camera_id": "TestGround", "source": self.source}}
        self.pixels = np.array([[100, 100], [900, 100], [900, 400], [100, 400]], dtype=float)
        self.local_ne = np.array([[-15, -40], [-15, 40], [15, 40], [15, -40]], dtype=float)
        world = self.geometry.local_to_wgs84(self.local_ne, (45.0, -73.0))
        self.document = self.api.create_calibration_document(self.pixels, world, 1000, 500,
                                                              camera_id="TestGround", source=self.source)
        write_json(folder / "TestGround.json", self.document)
        self.model = GroundCalibration(self.config, "synthetic", 1000, 500)

    def test_axes_and_normalized_pixels_are_not_swapped(self):
        result = self.model.project([700, 300])
        np.testing.assert_allclose([result["east_m"], result["north_m"]], [20, 5], atol=1e-5)
        recovered = self.model.local_coordinates([[result["latitude_deg"], result["longitude_deg"]]])
        np.testing.assert_allclose(recovered, [[20, 5]], atol=1e-5)

    def test_geographic_round_trip_uses_east_north_adapter_order(self):
        expected = np.array([[10, 4], [-12, 3]], dtype=float)
        world = self.model.world_coordinates(expected)
        np.testing.assert_allclose(self.model.local_coordinates(world), expected, atol=1e-6)

    def test_outside_polygon_is_invalid_not_zero_coordinates(self):
        result = project_record(self.model, [20, 20])
        self.assertFalse(result["projection_valid"])
        self.assertEqual(result["east_m"], "")
        self.assertIn("polygon", result["projection_reason"])

    def test_wrong_source_is_rejected(self):
        self.config["scenes"]["synthetic"]["source"] += ".other"
        with self.assertRaises(ValueError):
            GroundCalibration(self.config, "synthetic", 1000, 500)

    def test_wrong_aspect_ratio_is_rejected(self):
        with self.assertRaises(ValueError):
            GroundCalibration(self.config, "synthetic", 1000, 600)

    def test_missing_real_calibration_is_not_filled_with_synthetic_values(self):
        self.config["scenes"]["synthetic"]["camera_id"] = "NotAvailable"
        with self.assertRaises(FileNotFoundError):
            GroundCalibration(self.config, "synthetic", 1000, 500)

    def test_changed_calibration_is_detected_before_writing_projection(self):
        root = Path(self.directory.name)
        write_csv(root / "tracks" / "synthetic" / "tracks.csv", [{"x": 700, "y": 300}])
        changed = copy.deepcopy(self.document)
        changed["metadata"]["note"] = "changed after model load"
        write_json(self.model.path, changed)
        with self.assertRaisesRegex(ValueError, "changed during projection"):
            project_sequence("synthetic", self.model, root, 32, root / "output")
        self.assertFalse((root / "output" / "tracks_ground.csv").exists())


class MetricSubsetTests(unittest.TestCase):
    def test_visible_and_hidden_projections_must_both_be_valid(self):
        key = "object_pixels/video/1"
        item = {"video_id": "video", "track_id": "1", "kind": "object_pixels", "unit": "px",
                "frames": np.arange(6), "times": np.arange(6, dtype=float), "positions": np.zeros((6, 2))}
        masks = [{"series_id": key, "mask_id": key + "/m0", "visible_indices": [0, 3], "hidden_indices": [1, 2]},
                 {"series_id": key, "mask_id": key + "/m1", "visible_indices": [3, 5], "hidden_indices": [4]}]
        projected = {("video", "1", i): {"projection_valid": "True", "east_m": i, "north_m": 2 * i}
                     for i in range(6)}
        projected[("video", "1", 0)]["projection_valid"] = "False"
        original = copy.deepcopy(masks)
        ground, paired, metric, excluded = calibrated_cases({key: item}, {"masks": masks}, projected)
        self.assertEqual(masks, original)
        self.assertEqual(len(excluded), 1)
        self.assertEqual(paired[0]["hidden_indices"], [4])
        self.assertEqual(metric[0]["hidden_indices"], [4])
        np.testing.assert_allclose(ground["object_ground/video/1"]["positions"][4], [4, 8])
        projected[("video", "1", 4)]["projection_valid"] = "False"
        self.assertEqual(calibrated_cases({key: item}, {"masks": masks}, projected)[1], [])


if __name__ == "__main__":
    unittest.main()
