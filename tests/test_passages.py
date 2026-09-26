import unittest

import numpy as np

from src.passage_clips import candidates_for_track, motion_metrics


class PassageSelectionTests(unittest.TestCase):
    def test_stationary_jitter_is_not_a_vehicle_passage(self):
        t = np.arange(240) / 30
        positions = np.array([100, 150]) + np.random.default_rng(4).normal(0, 0.5, (len(t), 2))
        motion = motion_metrics(t, positions, np.full(len(t), 50.0))
        self.assertLess(motion["displacement_widths"], 0.05)
        self.assertLess(motion["moving_fraction"], 0.2)

    def test_constant_motion_is_identified(self):
        t = np.arange(240) / 30
        positions = np.column_stack((100 + 20 * t, 200 + 5 * t))
        motion = motion_metrics(t, positions, np.full(len(t), 40.0))
        self.assertGreater(motion["displacement_px"], 150)
        self.assertEqual(motion["moving_fraction"], 1.0)
        self.assertAlmostEqual(motion["directional_coherence"], 1.0)

    def test_no_clip_spans_a_naturally_missing_interval(self):
        frames = np.r_[np.arange(130), np.arange(180, 310)]
        rows = [{"frame": int(f), "timestamp_s": float(f / 30), "x": 100 + f,
                 "y": 200, "x_min": 80 + f, "x_max": 120 + f, "y_min": 170, "y_max": 200}
                for f in frames]
        config = {"minimum_seconds": 6, "target_seconds": 8, "candidate_stride_seconds": 2,
                  "minimum_masked_samples": 1, "minimum_median_height_px": 10,
                  "minimum_displacement_px": 10, "minimum_displacement_widths": 0.1,
                  "minimum_moving_fraction": 0.5, "minimum_directional_coherence": 0.5}
        candidates = candidates_for_track("test", "1", rows, set(frames), config, (800, 600))
        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
