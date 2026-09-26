import copy
import unittest

import numpy as np

from src.benchmark import validate_saved_masks
from src.interpolation import Interpolator
from src.methods import POLYNOMIAL_METHODS, VIDEO_METHODS


class CourseMethodsTests(unittest.TestCase):
    def test_affine_motion_and_physical_derivatives_for_every_video_method(self):
        times = np.array([100.0, 101.1, 102.4, 103.0, 106.0, 106.9, 107.5, 109.0])
        query = np.array([103.1, 104.3, 105.0, 105.9])
        for method in VIDEO_METHODS:
            with self.subTest(method=method):
                model = Interpolator(method).fit(times, 3 * times - 12)
                np.testing.assert_allclose(model.predict(query), 3 * query - 12, atol=1e-8)
                np.testing.assert_allclose(model.derivative(query), 3, atol=1e-8)

    def test_interpolation_at_nodes_for_every_video_method(self):
        times = np.array([0.0, 0.1, 0.2, 0.3, 1.2, 1.3, 1.4, 1.5])
        values = np.array([3.0, 2.0, 7.0, 3.0, 0.0, 2.0, -1.0, 5.0])
        for method in VIDEO_METHODS:
            with self.subTest(method=method):
                model = Interpolator(method).fit(times, values)
                np.testing.assert_allclose(model.predict(times), values, atol=1e-9)

    def test_polynomial_reproduction_and_independent_formulations_agree(self):
        t = np.array([2.0, 2.3, 2.9, 3.2, 4.5, 4.8, 5.1, 5.5])
        q = np.linspace(t[0], t[-1], 37)
        expected = lambda x: 0.2 * x ** 3 - 1.5 * x ** 2 + 2 * x - 1
        models = [Interpolator(method).fit(t, expected(t)) for method in POLYNOMIAL_METHODS]
        for model in models:
            np.testing.assert_allclose(model.predict(q), expected(q), atol=1e-9)
            np.testing.assert_allclose(model.derivative(q), 0.6 * q ** 2 - 3 * q + 2, atol=1e-8)
            np.testing.assert_allclose(model.derivative(q, 2), 1.2 * q - 3, atol=1e-8)
        noisy = np.random.default_rng(7).normal(size=len(t))
        estimates = [Interpolator(method).fit(t, noisy).predict(q) for method in POLYNOMIAL_METHODS]
        for estimate in estimates[1:]:
            np.testing.assert_allclose(estimate, estimates[0], rtol=1e-8, atol=1e-8)

    def test_clamped_estimates_quadratic_end_derivatives_from_visible_data(self):
        t = np.array([10.0, 11, 12, 18, 19, 20])
        q = np.linspace(12, 18, 17)
        model = Interpolator("s3_clamped").fit(t, 2 * t ** 2 - 3 * t)
        np.testing.assert_allclose(model.predict(q), 2 * q ** 2 - 3 * q, atol=1e-8)

    def test_clamped_physical_endpoint_derivatives_are_rescaled(self):
        t = np.array([10.0, 12, 16, 20])
        model = Interpolator("s3_clamped", endpoint_derivatives=(0, 300)).fit(t, (t - 10) ** 3)
        q = np.linspace(10, 20, 21)
        np.testing.assert_allclose(model.predict(q), (q - 10) ** 3, atol=1e-8)

    def test_periodic_spline_closes_value_velocity_and_acceleration(self):
        t = np.linspace(0, 6, 17)
        y = np.sin(2 * np.pi * t / 6)
        y[-1] = y[0]
        model = Interpolator("s3_periodic", period=6).fit(t, y)
        for order in range(3):
            endpoints = model.predict(np.array([0.0, 6.0]), order=order)
            self.assertAlmostEqual(endpoints[0], endpoints[1], places=10)
        with self.assertRaises(ValueError):
            Interpolator("s3_periodic").fit([0, 1, 2], [0, 1, 3])

    def test_trigonometric_odd_even_and_missing_samples(self):
        period, origin = 3.7, 10.0
        for count in (8, 9):
            full = origin + period * np.arange(count + 2) / (count + 2)
            t = np.delete(full, [3, 4])
            f = lambda s: 2 + np.sin(2 * np.pi * (s - origin) / period) + 0.3 * np.cos(4 * np.pi * (s - origin) / period)
            q = np.linspace(t[0], t[-1], 31)
            model = Interpolator("trigonometric", period=period, origin=origin).fit(t, f(t))
            np.testing.assert_allclose(model.predict(q), f(q), atol=1e-9)
            derivative = ((2 * np.pi / period) * np.cos(2 * np.pi * (q - origin) / period)
                          - (1.2 * np.pi / period) * np.sin(4 * np.pi * (q - origin) / period))
            np.testing.assert_allclose(model.derivative(q), derivative, atol=1e-8)
        with self.assertRaises(ValueError):
            Interpolator("trigonometric", period=2).fit([0, 1, 2], [0, 1, 0])

    def test_rational_reproduces_cubic_and_derivatives_including_at_nodes(self):
        t = np.array([0.0, 0.1, 0.2, 0.3, 1.1, 1.2, 1.3, 1.4])
        model = Interpolator("rational_fh").fit(t, t ** 3 - 2 * t + 1)
        q = np.r_[t, 0.6, 0.8]
        np.testing.assert_allclose(model.predict(q), q ** 3 - 2 * q + 1, atol=1e-9)
        np.testing.assert_allclose(model.derivative(q), 3 * q ** 2 - 2, atol=1e-8)
        np.testing.assert_allclose(model.derivative(q, 2), 6 * q, atol=1e-7)


class SavedMasksTests(unittest.TestCase):
    def test_changing_only_methods_preserves_the_original_manifest(self):
        old = {"config": {"methods": ["s1"]}, "masks": [{"hidden_frames": [5, 6]}], "source_sha256": {"data": "abc"}}
        new = copy.deepcopy(old)
        new["config"]["methods"] = list(VIDEO_METHODS)
        self.assertIs(validate_saved_masks(old, new), old)
        new["masks"][0]["hidden_frames"] = [6, 7]
        with self.assertRaises(ValueError):
            validate_saved_masks(old, new)
        new = copy.deepcopy(old)
        new["source_sha256"]["data"] = "changed"
        with self.assertRaises(ValueError):
            validate_saved_masks(old, new)


if __name__ == "__main__":
    unittest.main()
