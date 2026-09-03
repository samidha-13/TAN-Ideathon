"""
Tests for SRTM terrain provider.
"""
import sys
import os
import math
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from navigation.terrain_provider import SRTMTerrainProvider


class TestSRTMTerrainProvider(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.provider = SRTMTerrainProvider()

    @classmethod
    def tearDownClass(cls):
        cls.provider.close()

    # ── tile selection ──────────────────────────────────────────────────────

    def test_mountain_tile_selected(self):
        """Mountain mission coords (30.1, 78.2) should resolve in mountain tile."""
        elev = self.provider.get_elevation(30.1, 78.2)
        # Uttarakhand Himalayas: SRTM elevation for this specific point is ~400–1500 m
        # (elevation varies by exact sub-tile location; always positive and physically valid)
        self.assertIsInstance(elev, float)
        self.assertGreater(elev, 100.0, f"Mountain elevation unexpectedly low: {elev}")
        self.assertLess(elev, 9000.0)

    def test_desert_tile_selected(self):
        """Desert mission coords (26.7, 70.7) → Thar Desert, expect flat low terrain."""
        elev = self.provider.get_elevation(26.7, 70.7)
        self.assertIsInstance(elev, float)
        # Thar Desert typically 50–200 m
        self.assertLess(elev, 400.0, f"Desert elevation unexpectedly high: {elev}")
        self.assertGreater(elev, -10.0)

    def test_western_ghats_tile_selected(self):
        """Western Ghats coords (15.2, 73.9) → moderate terrain."""
        elev = self.provider.get_elevation(15.2, 73.9)
        self.assertIsInstance(elev, float)
        self.assertTrue(math.isfinite(elev))

    def test_flat_plain_tile_selected(self):
        """Flat Plain coords (25.2, 81.7) → Gangetic plain, expect low elevation."""
        elev = self.provider.get_elevation(25.2, 81.7)
        self.assertIsInstance(elev, float)
        # Gangetic plain typically 80–120 m
        self.assertLess(elev, 300.0, f"Flat plain elevation unexpectedly high: {elev}")
        self.assertGreater(elev, 0.0)

    # ── coordinate lookup ───────────────────────────────────────────────────

    def test_returns_finite_float(self):
        """All valid mission-area coordinates should return finite floats."""
        test_points = [
            (30.05, 78.05),   # mountain
            (30.27, 78.34),   # mountain edge
            (26.5,  70.5),    # desert
            (15.0,  73.7),    # western ghats SW
            (15.5,  74.2),    # western ghats NE
            (25.05, 81.55),   # flat plain SW
            (25.47, 81.94),   # flat plain NE
        ]
        for lat, lon in test_points:
            with self.subTest(lat=lat, lon=lon):
                elev = self.provider.get_elevation(lat, lon)
                self.assertTrue(
                    math.isfinite(elev),
                    f"Non-finite elevation at ({lat}, {lon}): {elev}",
                )

    def test_elevation_values_in_sane_range(self):
        """All returned elevations must be in physically plausible range."""
        for lat, lon in [(30.1, 78.2), (26.7, 70.7), (15.3, 74.0), (25.2, 81.7)]:
            elev = self.provider.get_elevation(lat, lon)
            self.assertGreater(elev, -500.0)
            self.assertLess(elev, 10_000.0)

    def test_no_tile_returns_fallback(self):
        """Coordinates with no tile should return fallback (0.0) without error."""
        provider = SRTMTerrainProvider(fallback_elevation=0.0)
        elev = provider.get_elevation(0.0, 0.0)  # Gulf of Guinea — no tile
        self.assertEqual(elev, 0.0)

    def test_boundary_coordinate(self):
        """Coordinate exactly on tile boundary should not raise."""
        # 30.0 N, 78.0 E is the SW corner of the mountain tile
        elev = self.provider.get_elevation(30.0, 78.0)
        self.assertTrue(math.isfinite(elev))

    # ── profile ──────────────────────────────────────────────────────────────

    def test_elevation_profile(self):
        """get_elevation_profile should return list of same length."""
        lats = [30.1, 30.12, 30.14]
        lons = [78.2, 78.22, 78.24]
        profile = self.provider.get_elevation_profile(lats, lons)
        self.assertEqual(len(profile), 3)
        for e in profile:
            self.assertTrue(math.isfinite(e))

    # ── radar integration ────────────────────────────────────────────────────

    def test_radar_agl_positive_for_mountain(self):
        """
        For an aircraft at 5000 m over mountain terrain (~2000 m),
        the radar AGL should be positive and less than 5000 m.
        """
        aircraft_alt = 5000.0
        terrain_elev = self.provider.get_elevation(30.1, 78.2)
        agl = aircraft_alt - terrain_elev
        self.assertGreater(agl, 0.0)
        self.assertLess(agl, aircraft_alt)


class TestSRTMTerrainProviderContext(unittest.TestCase):
    """Test context manager usage."""

    def test_context_manager(self):
        with SRTMTerrainProvider() as p:
            elev = p.get_elevation(30.1, 78.2)
            self.assertTrue(math.isfinite(elev))
        # After close — no error expected


if __name__ == "__main__":
    unittest.main()
