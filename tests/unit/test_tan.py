import unittest.mock
"""
Tests for TAN (Terrain-Aided Navigation) — profile-based NCC matching.
"""
import sys
import os
import math
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from navigation.tan import (
    TerrainAidedNavigation,
    ProfileSample,
    normalized_cross_correlation,
)
from navigation.terrain_provider import SRTMTerrainProvider
from navigation.terrain_observability import ObservabilityLevel, TerrainObservabilityResult


class _MockTerrainProvider:
    """Synthetic inclined terrain for TAN unit tests (no real files needed)."""
    def get_elevation(self, lat: float, lon: float) -> float:
        dlat = lat - 30.1
        dlon = lon - 78.2
        return 2000.0 + 500.0 * math.exp(-(dlat**2 + dlon**2) / 0.01)


def _build_profile(terrain, centre_lat, centre_lon, ins_alt, n=15, step=0.0001):
    """Build a profile along a short path with perfect radar measurements."""
    samples = []
    for i in range(n):
        lat = centre_lat + i * step
        lon = centre_lon + i * step * 0.5
        elev = terrain.get_elevation(lat, lon)
        samples.append(ProfileSample(
            ins_lat=lat, ins_lon=lon, ins_alt=ins_alt,
            radar_agl=ins_alt - elev,
        ))
    return samples


class TestNCC(unittest.TestCase):

    def test_identical_profiles_ncc_one(self):
        p = [100.0, 200.0, 150.0, 300.0]
        self.assertAlmostEqual(normalized_cross_correlation(p, p), 1.0, places=5)

    def test_anti_correlated_ncc_negative(self):
        p = [1.0, 2.0, 3.0, 4.0]
        q = [4.0, 3.0, 2.0, 1.0]
        self.assertLess(normalized_cross_correlation(p, q), 0.0)


class TestTANWithMockTerrain(unittest.TestCase):

    def setUp(self):
        self.terrain = _MockTerrainProvider()
        self.tan = TerrainAidedNavigation(
            self.terrain, search_radius_m=2000.0, grid_steps=7, min_profile_len=10
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
        profile = _build_profile(self.terrain, 30.1, 78.2, 5000.0)
        result = self.tan.compute(
            ins_lat=30.1, ins_lon=78.2, ins_alt=5000.0,
            profile=profile, obs_result=self._high_obs(),
        )
        self.assertTrue(result.valid, f"TAN should be valid: {result.reject_reason}")
        self.assertGreater(result.match_score, 0.7)
        self.assertTrue(math.isfinite(result.estimated_lat))
        self.assertTrue(math.isfinite(result.estimated_lon))

    def test_insufficient_profile_rejected(self):
        profile = _build_profile(self.terrain, 30.1, 78.2, 5000.0, n=5)
        result = self.tan.compute(
            ins_lat=30.1, ins_lon=78.2, ins_alt=5000.0,
            profile=profile, obs_result=self._high_obs(),
        )
        self.assertFalse(result.valid)
        self.assertIn("insufficient profile", result.reject_reason)

    def test_nan_radar_rejected(self):
        profile = _build_profile(self.terrain, 30.1, 78.2, 5000.0)
        profile[5] = ProfileSample(30.1, 78.2, 5000.0, float("nan"))
        result = self.tan.compute(
            ins_lat=30.1, ins_lon=78.2, ins_alt=5000.0,
            profile=profile, obs_result=self._high_obs(),
        )
        self.assertFalse(result.valid)

    @unittest.mock.patch('navigation.tan.normalized_cross_correlation')
    def test_low_observability_weak_match_rejected(self, mock_ncc):
        mock_ncc.return_value = 0.5
        low_obs = TerrainObservabilityResult(
            level=ObservabilityLevel.LOW,
            elevation_std_m=2.0,
            mean_abs_gradient=0.01,
            profile_length=21,
            score=0.01,
        )
        profile = _build_profile(self.terrain, 30.1, 78.2, 5000.0)
        result = self.tan.compute(
            ins_lat=30.1, ins_lon=78.2, ins_alt=5000.0,
            profile=profile, obs_result=low_obs,
        )
        self.assertFalse(result.valid)

    def test_low_observability_strong_match_accepted(self):
        low_obs = TerrainObservabilityResult(
            level=ObservabilityLevel.LOW,
            elevation_std_m=2.0,
            mean_abs_gradient=0.01,
            profile_length=21,
            score=0.01,
        )
        # Perfect profile creates strong match (NCC = 1.0)
        profile = _build_profile(self.terrain, 30.1, 78.2, 5000.0)
        result = self.tan.compute(
            ins_lat=30.1, ins_lon=78.2, ins_alt=5000.0,
            profile=profile, obs_result=low_obs,
        )
        self.assertTrue(result.valid)
        self.assertGreater(result.match_score, 0.90)

    def test_n_candidates_nonzero(self):
        profile = _build_profile(self.terrain, 30.1, 78.2, 5000.0)
        result = self.tan.compute(
            ins_lat=30.1, ins_lon=78.2, ins_alt=5000.0,
            profile=profile, obs_result=self._high_obs(),
        )
        if result.valid:
            self.assertGreater(result.n_candidates, 1)


class TestTANWithRealSRTM(unittest.TestCase):
    """Integration test with real SRTM data — mountain mission."""

    @classmethod
    def setUpClass(cls):
        cls.provider = SRTMTerrainProvider()
        cls.tan = TerrainAidedNavigation(
            cls.provider, search_radius_m=3000.0, grid_steps=9, min_profile_len=10
        )

    @classmethod
    def tearDownClass(cls):
        cls.provider.close()

    def test_mountain_tan_produces_result(self):
        lat, lon = 30.1, 78.2
        alt = 5000.0
        profile = _build_profile(self.provider, lat, lon, alt, n=15, step=0.0002)
        result = self.tan.compute(lat, lon, alt, profile)
        self.assertIsNotNone(result)
        self.assertIsInstance(result.valid, bool)

    def test_flat_plain_tan_rejected_or_low_confidence(self):
        lat, lon = 25.2, 81.7
        alt = 2000.0
        profile = _build_profile(self.provider, lat, lon, alt, n=15, step=0.0002)
        result = self.tan.compute(lat, lon, alt, profile)
        if result.valid:
            self.assertIsInstance(result.match_score, float)
        else:
            self.assertTrue(
                "LOW" in result.reject_reason or "NCC" in result.reject_reason
            )


if __name__ == "__main__":
    unittest.main()
