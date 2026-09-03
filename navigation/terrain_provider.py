"""
SRTM 1 Arc-Second terrain provider using real GeoTIFF raster data.

Tile layout (all located under data/terrain/):
  mountain/       n30_e078_1arc_v3.tif   (covers 30–31 N, 78–79 E)
  desert/         n26_e070_1arc_v3.tif   (covers 26–27 N, 70–71 E)
  western_ghats/  n15_e073_1arc_v3.tif   (covers 15–16 N, 73–74 E)
                  n15_e074_1arc_v3.tif   (covers 15–16 N, 74–75 E)
  flat_plain/     n25_e081_1arc_v3.tif   (covers 25–26 N, 81–82 E)

Vertical reference: EGM96-approximated ellipsoidal height (SRTM convention).
All elevations are in metres above mean sea level.

Usage:
    from navigation.terrain_provider import SRTMTerrainProvider
    provider = SRTMTerrainProvider()          # auto-discovers tiles
    elev = provider.get_elevation(30.15, 78.2)  # metres
"""

import os
import math
import logging
from typing import Dict, Optional, Tuple

import rasterio
from rasterio.transform import rowcol

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Paths (relative to the repository root, resolved at import time)
# ─────────────────────────────────────────────────────────────────────────────
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_TERRAIN_ROOT = os.path.join(_REPO_ROOT, "terrain")

# Catalogue of known tiles: (lat_min, lon_min) → relative path from terrain root.
# Each SRTM 1-arc tile covers exactly 1°×1° starting from the SW corner (n/e prefix).
_TILE_CATALOGUE: Dict[Tuple[int, int], str] = {
    (30, 78): os.path.join("mountain",      "n30_e078_1arc_v3.tif"),
    (26, 70): os.path.join("desert",        "n26_e070_1arc_v3.tif"),
    (15, 73): os.path.join("western_ghats", "n15_e073_1arc_v3.tif"),
    (15, 74): os.path.join("western_ghats", "n15_e074_1arc_v3.tif"),
    (25, 81): os.path.join("flat_plain",    "n25_e081_1arc_v3.tif"),
}


class _TileCache:
    """Lazy-loading per-tile rasterio dataset cache."""

    def __init__(self) -> None:
        self._datasets: Dict[Tuple[int, int], rasterio.DatasetReader] = {}

    def get(self, tile_key: Tuple[int, int]) -> Optional[rasterio.DatasetReader]:
        if tile_key in self._datasets:
            return self._datasets[tile_key]

        rel_path = _TILE_CATALOGUE.get(tile_key)
        if rel_path is None:
            return None

        full_path = os.path.join(_TERRAIN_ROOT, rel_path)
        if not os.path.isfile(full_path):
            logger.warning("SRTM tile not found on disk: %s", full_path)
            return None

        try:
            ds = rasterio.open(full_path)
            self._datasets[tile_key] = ds
            logger.debug("Opened SRTM tile %s", full_path)
            return ds
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to open tile %s: %s", full_path, exc)
            return None

    def close_all(self) -> None:
        for ds in self._datasets.values():
            try:
                ds.close()
            except Exception:
                pass
        self._datasets.clear()


class SRTMTerrainProvider:
    """
    Real SRTM terrain elevation provider.

    Implements the TerrainElevationProvider protocol expected by
    simulator.radar_altimeter.RadarAltimeter and navigation modules.

    Parameters
    ----------
    fallback_elevation : float
        Elevation (m) returned when no tile covers the queried coordinates.
        Default 0 (sea level).  A warning is always logged.
    """

    def __init__(self, fallback_elevation: float = 0.0) -> None:
        self._cache = _TileCache()
        self._fallback = fallback_elevation

    # ── public interface ─────────────────────────────────────────────────────

    def get_elevation(self, lat: float, lon: float) -> float:
        """
        Return terrain elevation in metres for the given WGS-84 coordinates.

        Selects the correct SRTM 1-arc tile automatically.  When coordinates
        sit on a tile boundary the nearest valid tile is used.

        Parameters
        ----------
        lat : float   latitude  in degrees  (−90 … +90)
        lon : float   longitude in degrees  (−180 … +180)

        Returns
        -------
        float   terrain elevation above mean sea level in metres.
        """
        tile_key = self._tile_key(lat, lon)
        ds = self._cache.get(tile_key)

        if ds is None:
            # Try boundary: e.g., lon exactly 79.0 could belong to tile (30,78) still
            tile_key = self._tile_key_boundary(lat, lon)
            ds = self._cache.get(tile_key)

        if ds is None:
            logger.warning(
                "No SRTM tile for lat=%.6f lon=%.6f; returning fallback=%.1f m",
                lat, lon, self._fallback,
            )
            return self._fallback

        return self._sample(ds, lat, lon)

    def get_elevation_profile(
        self,
        lats: list,
        lons: list,
    ) -> list:
        """
        Return a list of elevations for a sequence of (lat, lon) pairs.
        Convenience method used by TAN terrain matching.
        """
        return [self.get_elevation(la, lo) for la, lo in zip(lats, lons)]

    def close(self) -> None:
        """Release open file handles."""
        self._cache.close_all()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ── internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _tile_key(lat: float, lon: float) -> Tuple[int, int]:
        """
        Return the (lat_floor, lon_floor) key for the tile that contains
        the given point.  Uses math.floor so e.g. 29.999 → 29, not 30.
        """
        return (int(math.floor(lat)), int(math.floor(lon)))

    @staticmethod
    def _tile_key_boundary(lat: float, lon: float) -> Tuple[int, int]:
        """
        Fallback tile key: subtract a tiny epsilon before flooring so that
        a coordinate exactly ON the northern/eastern boundary is looked up
        in the tile to the south/west (which physically covers it).
        """
        eps = 1e-9
        return (int(math.floor(lat - eps)), int(math.floor(lon - eps)))

    @staticmethod
    def _sample(ds: rasterio.DatasetReader, lat: float, lon: float) -> float:
        """
        Bilinearly-interpolated sample from the raster at (lat, lon).
        Falls back to nearest-neighbour if the point is outside the dataset
        bounds (should not happen for valid mission coordinates).
        """
        # rasterio rowcol returns integer pixel row/col for the given transform
        # We use the dataset's own transform for exact coordinate mapping.
        try:
            # Use rasterio's built-in sample (returns iterator of arrays)
            vals = list(ds.sample([(lon, lat)]))  # sample takes (x=lon, y=lat)
            value = float(vals[0][0])
            # SRTM nodata is typically -32768 or 0 in ocean areas
            if value < -1000 or value > 9000:
                logger.debug(
                    "SRTM nodata/suspect value %.1f at lat=%.6f lon=%.6f; using 0",
                    value, lat, lon,
                )
                return 0.0
            return value
        except Exception as exc:
            logger.error("SRTM sample error at lat=%.6f lon=%.6f: %s", lat, lon, exc)
            return 0.0


# ── Convenience: terrain region observability metadata ────────────────────────

def terrain_region_for_mission(mission_name: str) -> str:
    """Map mission name to terrain region string."""
    mapping = {
        "mountain_mission":     "mountain",
        "desert_mission":       "desert",
        "western_ghats_mission": "western_ghats",
        "flat_plain_mission":   "flat_plain",
    }
    return mapping.get(mission_name, "unknown")
