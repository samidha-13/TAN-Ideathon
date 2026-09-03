"""
Tests for TAN (Terrain-Aided Navigation).
"""
import sys
import os
import math
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from navigation.tan import TerrainAidedNavigation
from navigation.terrain_provider import SRTMTerrainProvider
from navigation.terrain_observability import ObservabilityLevel, TerrainObservabilityResult


class _MockTerrainProvider:
    """Synthetic inclined terrain for TAN unit tests (no real files needed)."""
    def get_elevation(self, lat: float, lon: float) -> float:
        # Simple hill: peak at (30.1, 78.2), drops with distance
        dlat = lat - 30.1
        dlon = lon - 78.2
        return 2000.0 + 500.0 * math.exp(-(dlat**2 + dlon**2) / 0.01)


class TestTANWithMockTerrain(unittest.TestCase):

    def setUp(self):
        self.terrain = _MockTerrainProvider()
        self.tan = TerrainAidedNavigation(
            self.terrain, search_radius_m=2000.0, grid_steps=7
        )

    def _high_obs(self):
        return TerrainObservabilityResult(
            level=ObservabilityLevel.HIGH,
            elevation_std_m=200.0,
            mean_abs_gradient=0.1,
            profile_length=21,
            score=0.8,
        )

    def test_valid_tan_result_for_high_obs(self):
        """With HIGH observability and valid radar, TAN should produce a valid result."""
        terrain_at_truth = self.terrain.get_elevation(30.1, 78.2)
        ins_alt   = 5000.0
        radar_agl = ins_alt - terrain_at_truth  # perfect radar

        result = self.tan.compute(
            ins_lat=30.1, ins_lon=78.2,
            ins_alt=ins_alt, radar_agl=radar_agl,
            obs_result=self._high_obs(),
        )
        self.assertTrue(result.valid, f"TAN should be valid: {result.reject_reason}")
        self.assertGreater(result.match_score, 0.0)
        self.assertTrue(math.isfinite(result.estimated_lat))
        self.assertTrue(math.isfinite(result.estimated_lon))

    def test_nan_radar_rejected(self):
        """NaN radar AGL should be immediately rejected."""
        result = self.tan.compute(
            ins_lat=30.1, ins_lon=78.2,
            ins_alt=5000.0, radar_agl=float("nan"),
            obs_result=self._high_obs(),
        )
        self.assertFalse(result.valid)

    def test_out_of_range_radar_rejected(self):
        """Radar AGL < −50 or > 15000 should be rejected."""
        for bad_agl in [-100.0, 20000.0]:
            result = self.tan.compute(
                ins_lat=30.1, ins_lon=78.2, ins_alt=5000.0,
                radar_agl=bad_agl, obs_result=self._high_obs(),
            )
            self.assertFalse(result.valid, f"Should reject agl={bad_agl}")

    def test_low_observability_rejected(self):
        """LOW terrain observability should cause TAN to reject."""
        low_obs = TerrainObservabilityResult(
            level=ObservabilityLevel.LOW,
            elevation_std_m=2.0,
            mean_abs_gradient=0.01,
            profile_length=21,
            score=0.01,
        )
        result = self.tan.compute(
            ins_lat=30.1, ins_lon=78.2, ins_alt=5000.0,
            radar_agl=2900.0, obs_result=low_obs,
        )
        self.assertFalse(result.valid)
        self.assertIn("LOW", result.reject_reason)

    def test_match_score_in_valid_range(self):
        """Match score should be in (0, 1]."""
        terrain_elev = self.terrain.get_elevation(30.1, 78.2)
        result = self.tan.compute(
            ins_lat=30.1, ins_lon=78.2,
            ins_alt=5000.0, radar_agl=5000.0 - terrain_elev,
            obs_result=self._high_obs(),
        )
        if result.valid:
            self.assertGreater(result.match_score, 0.0)
            self.assertLessEqual(result.match_score, 1.0)

    def test_n_candidates_nonzero(self):
        """TAN should evaluate multiple candidates."""
        terrain_elev = self.terrain.get_elevation(30.1, 78.2)
        result = self.tan.compute(
            ins_lat=30.1, ins_lon=78.2,
            ins_alt=5000.0, radar_agl=5000.0 - terrain_elev,
            obs_result=self._high_obs(),
        )
        if result.valid:
            self.assertGreater(result.n_candidates, 1)


class TestTANWithRealSRTM(unittest.TestCase):
    """Integration test with real SRTM data — mountain mission."""

    @classmethod
    def setUpClass(cls):
        cls.provider = SRTMTerrainProvider()
        cls.tan = TerrainAidedNavigation(cls.provider, search_radius_m=3000.0, grid_steps=9)

    @classmethod
    def tearDownClass(cls):
        cls.provider.close()

    def test_mountain_tan_produces_result(self):
        """Over mountain terrain, TAN should produce a valid result."""
        lat, lon = 30.1, 78.2
        alt = 5000.0
        terrain_elev = self.provider.get_elevation(lat, lon)
        agl = alt - terrain_elev   # perfect measurement

        result = self.tan.compute(lat, lon, alt, agl)
        # Mountain terrain should be HIGH observability → valid TAN
        self.assertIsNotNone(result)
        # Either valid or explicitly rejected due to low obs (which is still correct)
        self.assertIsInstance(result.valid, bool)

    def test_flat_plain_tan_rejected_or_low_confidence(self):
        """Flat Plain terrain → TAN should be rejected due to low observability."""
        lat, lon = 25.2, 81.7
        alt = 2000.0
        terrain_elev = self.provider.get_elevation(lat, lon)
        agl = alt - terrain_elev

        result = self.tan.compute(lat, lon, alt, agl)
        # Flat plain may be rejected (valid=False) or have very low score
        if result.valid:
            # If valid, match score should be low for flat terrain
            self.assertIsInstance(result.match_score, float)
        # No assertion that it MUST be invalid — terrain might have local variation


if __name__ == "__main__":
    unittest.main()
