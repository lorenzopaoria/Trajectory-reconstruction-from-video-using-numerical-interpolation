import copy
import unittest

import numpy as np

from src.benchmark import aggregate, evaluate
from src.coordinates import geodetic_to_enu
from src.gaps import make_continuous_masks, make_masks
from src.interpolation import Interpolator
from src.methods import VIDEO_METHODS


class InterpolationTests(unittest.TestCase):
    def test_affine_motion_and_physical_time_derivatives(self):
        times = np.array([120.0, 121.5, 125.0, 131.0, 134.0])
        query = np.array([122.0, 128.0, 133.0])
        for method in ("s1", "s2", "s3_natural"):
            with self.subTest(method=method):
                model = Interpolator(method).fit(times, 7 * times - 3)
                np.testing.assert_allclose(model.predict(query), 7 * query - 3, atol=1e-10)
                np.testing.assert_allclose(model.derivative(query), 7, atol=1e-10)

    def test_all_methods_interpolate_observations(self):
        times = np.array([0.0, 0.4, 1.8, 2.0, 4.5])
        values = np.array([3.0, -1, 7, 2, 0])
        for method in ("s1", "s2", "s3_natural"):
            model = Interpolator(method).fit(times, values)
            np.testing.assert_allclose(model.predict(times), values, atol=1e-10)

    def test_quadratic_spline_has_continuous_velocity(self):
        times = np.array([0.0, 1.0, 2.5, 4.0])
        model = Interpolator("s2").fit(times, [0, 2, -1, 5])
        for knot in times[1:-1]:
            self.assertAlmostEqual(float(model.derivative(knot - 1e-8)),
                                   float(model.derivative(knot + 1e-8)), places=5)
        self.assertAlmostEqual(float(model.derivative(0.5, order=2)), 0, places=10)

    def test_s1_velocity_at_internal_knot_is_not_reported_as_smooth(self):
        model = Interpolator("s1").fit([0, 1, 2], [0, 1, -1])
        self.assertTrue(np.isnan(model.derivative(1)))

    def test_invalid_inputs_and_extrapolation_are_rejected(self):
        for times, values in (([0, 0], [1, 2]), ([1, 0], [1, 2]), ([0, 1], [1, np.nan])):
            with self.assertRaises(ValueError):
                Interpolator("s1").fit(times, values)
        with self.assertRaises(ValueError):
            Interpolator("s1").fit([0, 1], [1, 2]).predict([-0.01])


class MaskTests(unittest.TestCase):
    def test_continuous_schedule_spans_entire_track_without_hidden_support(self):
        frames = np.arange(1000)
        args = (frames, frames / 30, [3, 6, 12, 24], 4, 42)
        masks = make_continuous_masks(*args)
        self.assertEqual(masks, make_continuous_masks(*args))
        self.assertGreater(len(masks), 50)
        hidden = [f for mask in masks for f in mask["hidden_frames"]]
        visible = {f for mask in masks for f in mask["visible_frames"]}
        self.assertEqual(len(hidden), len(set(hidden)))
        self.assertFalse(set(hidden) & visible)
        self.assertEqual(min(hidden), 4)
        self.assertGreater(max(hidden), 990)

    def test_continuous_schedule_does_not_cross_natural_holes(self):
        frames = np.r_[np.arange(35), np.arange(60, 110)]
        masks = make_continuous_masks(frames, frames / 30, [3, 12], 4, 5)
        self.assertTrue(masks)
        for mask in masks:
            window = sorted(mask["hidden_frames"] + mask["visible_frames"])
            self.assertTrue(np.all(np.diff(window) == 1))

    def test_all_continuous_hidden_values_are_excluded_from_every_fit(self):
        frames = np.arange(120)
        key = "test/continuous"
        item = {"frames": frames, "times": frames / 30,
                "positions": np.column_stack((np.sin(frames / 10), frames.astype(float))),
                "kind": "object_pixels", "video_id": "test", "track_id": "1", "unit": "px"}
        masks = make_continuous_masks(frames, frames / 30, [3, 12], 4, 5)
        for i, mask in enumerate(masks):
            mask.update(series_id=key, mask_id=f"continuous-{i}")
        manifest = {"masks": masks}
        _, original = evaluate({key: item}, manifest, VIDEO_METHODS)
        poisoned = copy.deepcopy(item)
        all_hidden = [i for mask in masks for i in mask["hidden_indices"]]
        poisoned["positions"][all_hidden] += 1e6
        _, changed = evaluate({key: poisoned}, manifest, VIDEO_METHODS)
        self.assertEqual([(r["predicted_x"], r["predicted_y"]) for r in original],
                         [(r["predicted_x"], r["predicted_y"]) for r in changed])

    def test_masks_are_reproducible_disjoint_and_bracketed(self):
        args = (np.arange(40), np.arange(40) * 0.1, [1, 5, 10], 4, 5, 23)
        masks = make_masks(*args)
        self.assertEqual(masks, make_masks(*args))
        self.assertEqual(len(masks), 15)
        for mask in masks:
            self.assertFalse(set(mask["visible_indices"]) & set(mask["hidden_indices"]))
            self.assertEqual(len(mask["visible_indices"]), 8)
            self.assertLess(min(mask["visible_frames"]), min(mask["hidden_frames"]))
            self.assertGreater(max(mask["visible_frames"]), max(mask["hidden_frames"]))

    def test_naturally_missing_frames_are_not_used_as_reference(self):
        frames = np.array([0, 1, 2, 10, 11, 12])
        self.assertEqual(make_masks(frames, frames / 10, [2], 2, 4, 0), [])

    def test_hidden_values_cannot_change_predictions(self):
        frames = np.arange(20)
        key = "test/track"
        positions = np.column_stack((frames ** 2, np.sin(frames)))
        item = {"frames": frames, "times": frames / 10, "positions": positions,
                "kind": "object_pixels", "video_id": "test", "track_id": "1", "unit": "px"}
        mask = make_masks(frames, frames / 10, [5], 4, 1, 0)[0]
        mask.update(series_id=key, mask_id="test-mask")
        manifest = {"masks": [mask]}
        methods = ["s1", "s2", "s3_natural"]
        _, before = evaluate({key: item}, manifest, methods)
        poisoned = copy.deepcopy(item)
        poisoned["positions"][mask["hidden_indices"]] += 1000000
        _, after = evaluate({key: poisoned}, manifest, methods)
        self.assertEqual(len(before), 15)
        for left, right in zip(before, after):
            self.assertEqual(left["predicted_x"], right["predicted_x"])
            self.assertEqual(left["predicted_y"], right["predicted_y"])
            self.assertNotEqual(left["position_error"], right["position_error"])


class GeographyTests(unittest.TestCase):
    def test_origin_maps_to_zero(self):
        point = geodetic_to_enu([49.01], [8.42])
        np.testing.assert_allclose(point, [[0, 0, 0]], atol=1e-8)

    def test_known_equatorial_east_and_north_distances(self):
        points = geodetic_to_enu([0, 0, 0.001], [0, 0.001, 0])
        self.assertAlmostEqual(points[1, 0], 111.31949, places=4)
        self.assertAlmostEqual(points[2, 1], 110.57428, places=4)
        self.assertAlmostEqual(points[1, 1], 0, places=8)
        self.assertAlmostEqual(points[2, 0], 0, places=8)

    def test_bad_latitude_is_rejected(self):
        with self.assertRaises(ValueError):
            geodetic_to_enu([100], [8])


class AggregationTests(unittest.TestCase):
    def test_failed_trials_reduce_coverage(self):
        base = {"kind": "object_pixels", "unit": "px", "method": "s1", "gap_size": 2,
                "video_id": "test", "track_id": "1", "n_points": 2}
        rows = [dict(base, status="ok", n_valid=2, ade=3.0, squared_error_sum=20.0),
                dict(base, status="failed", n_valid=0, ade="", squared_error_sum="")]
        summary = aggregate(rows)[0]
        self.assertEqual(summary["coverage"], 0.5)
        self.assertEqual(summary["failed_masks"], 1)
        self.assertAlmostEqual(summary["micro_rms_position"], np.sqrt(10))


if __name__ == "__main__":
    unittest.main()
