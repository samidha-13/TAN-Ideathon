"""
Tests for terrain observability.
"""
import sys
import os
import math
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from navigation.terrain_observability import (
    compute_observability,
    ObservabilityLevel,
    sample_elevation_profile_around,
)
from navigation.terrain_provider import SRTMTerrainProvider


class TestComputeObservability(unittest.TestCase):

    def test_flat_profile_is_low(self):
        """Completely flat profile → LOW observability."""
        elevs = [100.0] * 20
        result = compute_observability(elevs)
        self.assertEqual(result.level, ObservabilityLevel.LOW)
        self.assertAlmostEqual(result.elevation_std_m, 0.0, places=5)

    def test_very_varied_profile_is_high(self):
        """Mountainous profile (large std) → HIGH observability."""
        import random
        rng = random.Random(42)
        elevs = [rng.uniform(1000, 4000) for _ in range(30)]
        result = compute_observability(elevs)
        self.assertEqual(result.level, ObservabilityLevel.HIGH)
        self.assertGreater(result.score, 0.5)

    def test_medium_variation(self):
        """Moderate elevation variation → MEDIUM observability."""
        # std around 30 m (between thresholds)
        elevs = [100 + 30 * math.sin(i * 0.5) for i in range(20)]
        result = compute_observability(elevs)
        self.assertIn(result.level, [ObservabilityLevel.MEDIUM, ObservabilityLevel.LOW])

    def test_single_point_is_low(self):
        """Single elevation sample → LOW (insufficient data)."""
        result = compute_observability([500.0])
        self.assertEqual(result.level, ObservabilityLevel.LOW)

    def test_score_in_0_1(self):
        """Score should always be in [0, 1]."""
        for elevs in [
            [100.0] * 10,
            [100 + i * 50 for i in range(20)],
            [5000, 100, 4000, 200, 3000],
        ]:
            result = compute_observability(elevs)
            self.assertGreaterEqual(result.score, 0.0)
            self.assertLessEqual(result.score, 1.0)

    def test_profile_length_stored(self):
        """profile_length should match input length."""
        elevs = [100.0 + i for i in range(15)]
        result = compute_observability(elevs)
        self.assertEqual(result.profile_length, 15)


class TestSRTMObservability(unittest.TestCase):
    """Integration tests: real terrain → observability classification."""

    @classmethod
    def setUpClass(cls):
        cls.provider = SRTMTerrainProvider()

    @classmethod
    def tearDownClass(cls):
        cls.provider.close()

    def test_mountain_observability_high(self):
        """Mountain terrain (30.1, 78.2) should be HIGH observability."""
        elevs, spacing = sample_elevation_profile_around(
            self.provider, 30.1, 78.2, radius_m=2000.0, n_points=21
        )
        result = compute_observability(elevs, spacing)
        self.assertIn(result.level, [ObservabilityLevel.HIGH, ObservabilityLevel.MEDIUM],
                      f"Mountain observability unexpectedly low: {result}")

    def test_flat_plain_observability(self):
        """Flat Plain (25.2, 81.7) should be LOW or MEDIUM observability."""
        elevs, spacing = sample_elevation_profile_around(
            self.provider, 25.2, 81.7, radius_m=2000.0, n_points=21
        )
        result = compute_observability(elevs, spacing)
        # Should NOT be HIGH for flat Gangetic plain
        self.assertNotEqual(
            result.level, ObservabilityLevel.HIGH,
            f"Flat plain unexpectedly HIGH: std={result.elevation_std_m:.1f}m",
        )


if __name__ == "__main__":
    unittest.main()
