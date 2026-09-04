"""
Terrain-Aided Navigation (TAN) module.

Algorithm: Point-Mass Filter / terrain-profile matching.

Given:
  - INS predicted position (lat_ins, lon_ins)
  - Radar altimeter height-above-ground (AGL) measurement
  - SRTM terrain database

Workflow
--------
1. Generate a grid of candidate positions around the INS estimate.
2. For each candidate, predict what the radar AGL reading should be:
       predicted_AGL = INS_altitude – SRTM_terrain_elevation(candidate_lat, candidate_lon)
3. Compute match score (inverse squared residual between predicted and measured AGL).
4. Best-matching candidate → TAN position measurement fed to EKF.

The TAN module does NOT receive the ground-truth trajectory.
The radar measurement is the only terrain-height observable; terrain geometry
from SRTM is the only spatial reference.

Diagnostics stored:
  - match_score        : quality of the best match (higher → more confident)
  - best_candidate     : (lat, lon) of best-matching candidate
  - residual_m         : AGL residual at best candidate (metres)
  - search_radius_m    : search window half-width used
  - n_candidates       : total number of candidates evaluated
"""

import math
import logging
from dataclasses import dataclass
from typing import Optional, Tuple, List

from navigation.terrain_observability import (
    ObservabilityLevel,
    TerrainObservabilityResult,
    compute_observability,
    sample_elevation_profile_around,
)

logger = logging.getLogger(__name__)

# ── defaults ──────────────────────────────────────────────────────────────────
_DEFAULT_SEARCH_RADIUS_M = 3_000.0   # ±3 km search window
_DEFAULT_GRID_STEPS      = 11        # 11×11 candidate grid
_MIN_AGL_M               = -50.0     # sanity: radar can't be <−50 m
_MAX_AGL_M               = 15_000.0  # sanity: can't be > 15 km
# Match score threshold below which TAN result is considered low-quality
_MIN_MATCH_SCORE         = 0.01


@dataclass
class TANResult:
    """Result of one TAN measurement computation."""
    valid:            bool           # whether a usable measurement was produced
    estimated_lat:    float          # best-match latitude  (degrees)
    estimated_lon:    float          # best-match longitude (degrees)
    match_score:      float          # 0…1, higher = better match
    residual_m:       float          # AGL residual at best candidate (m)
    search_radius_m:  float
    n_candidates:     int
    terrain_obs:      Optional[TerrainObservabilityResult] = None
    reject_reason:    str = ""       # non-empty if valid=False


class TerrainAidedNavigation:
    """
    Terrain-Aided Navigation using SRTM DEM + radar altimeter.

    Parameters
    ----------
    terrain_provider : SRTMTerrainProvider
    search_radius_m  : half-width of the candidate search window (metres)
    grid_steps       : number of grid points per axis (odd integer preferred)
    """

    def __init__(
        self,
        terrain_provider,
        search_radius_m: float = _DEFAULT_SEARCH_RADIUS_M,
        grid_steps: int = _DEFAULT_GRID_STEPS,
    ) -> None:
        self._terrain    = terrain_provider
        self._radius     = search_radius_m
        self._grid_steps = grid_steps

        # Flat-Earth conversion constants (approximated; updated per call)
        self._R = 6_371_000.0

    # ── public interface ──────────────────────────────────────────────────────

    def compute(
        self,
        ins_lat:     float,
        ins_lon:     float,
        ins_alt:     float,  # metres (aircraft altitude MSL)
        radar_agl:   float,  # metres (radar height-above-ground measurement)
        obs_result:  Optional[TerrainObservabilityResult] = None,
    ) -> TANResult:
        """
        Compute a TAN position measurement.

        Parameters
        ----------
        ins_lat   : INS predicted latitude  (degrees)
        ins_lon   : INS predicted longitude (degrees)
        ins_alt   : INS predicted altitude  (metres, MSL)
        radar_agl : Radar altimeter AGL measurement (metres)
        obs_result: pre-computed terrain observability (optional; computed here if None)

        Returns
        -------
        TANResult
        """
        # ── 0. Sanity-check radar reading ─────────────────────────────────────
        if not math.isfinite(radar_agl):
            return self._reject("radar_agl is NaN/Inf")
        if radar_agl < _MIN_AGL_M or radar_agl > _MAX_AGL_M:
            return self._reject(f"radar_agl={radar_agl:.1f} m out of valid range")

        # ── 1. Compute / check terrain observability ──────────────────────────
        if obs_result is None:
            elevs, spacing = sample_elevation_profile_around(
                self._terrain, ins_lat, ins_lon,
                radius_m=self._radius, n_points=self._grid_steps,
            )
            obs_result = compute_observability(elevs, spacing)

        if obs_result.level == ObservabilityLevel.LOW:
            return self._reject(
                "terrain observability LOW; TAN measurement downweighted/rejected",
                obs=obs_result,
            )

        # ── 2. Build candidate grid ───────────────────────────────────────────
        candidates = self._build_grid(ins_lat, ins_lon)
        if not candidates:
            return self._reject("candidate grid is empty")

        # ── 3. Score each candidate ───────────────────────────────────────────
        best_score  = -1.0
        best_lat    = ins_lat
        best_lon    = ins_lon
        best_resid  = float("inf")

        for (c_lat, c_lon) in candidates:
            terrain_elev = self._terrain.get_elevation(c_lat, c_lon)
            # Predicted AGL for this candidate position
            pred_agl = ins_alt - terrain_elev
            resid    = radar_agl - pred_agl
            score    = 1.0 / (1.0 + resid ** 2)   # Cauchy-like, always positive

            if score > best_score:
                best_score = score
                best_lat   = c_lat
                best_lon   = c_lon
                best_resid = resid

        # ── 4. Quality gate ───────────────────────────────────────────────────
        if best_score < _MIN_MATCH_SCORE:
            return self._reject(
                f"TAN match score {best_score:.4f} below threshold",
                obs=obs_result,
            )

        logger.debug(
            "TAN match: best=(%.6f, %.6f) score=%.4f resid=%.2fm obs=%s",
            best_lat, best_lon, best_score, best_resid, obs_result.level.value,
        )

        return TANResult(
            valid           = True,
            estimated_lat   = best_lat,
            estimated_lon   = best_lon,
            match_score     = best_score,
            residual_m      = best_resid,
            search_radius_m = self._radius,
            n_candidates    = len(candidates),
            terrain_obs     = obs_result,
        )

    # ── private helpers ───────────────────────────────────────────────────────

    def _build_grid(
        self, centre_lat: float, centre_lon: float
    ) -> List[Tuple[float, float]]:
        """Generate a regular grid of (lat, lon) candidates."""
        m_per_deg_lat = math.pi / 180.0 * self._R
        m_per_deg_lon = math.pi / 180.0 * self._R * math.cos(
            math.radians(centre_lat)
        )
        if m_per_deg_lat == 0 or m_per_deg_lon == 0:
            return []

        step = (2 * self._radius) / (self._grid_steps - 1) if self._grid_steps > 1 else self._radius
        half = self._radius

        candidates = []
        for i in range(self._grid_steps):
            for j in range(self._grid_steps):
                d_n = -half + i * step
                d_e = -half + j * step
                c_lat = centre_lat + d_n / m_per_deg_lat
                c_lon = centre_lon + d_e / m_per_deg_lon
                candidates.append((c_lat, c_lon))
        return candidates

    @staticmethod
    def _reject(reason: str, obs: Optional[TerrainObservabilityResult] = None) -> TANResult:
        logger.debug("TAN rejected: %s", reason)
        return TANResult(
            valid           = False,
            estimated_lat   = float("nan"),
            estimated_lon   = float("nan"),
            match_score     = 0.0,
            residual_m      = float("nan"),
            search_radius_m = 0.0,
            n_candidates    = 0,
            terrain_obs     = obs,
            reject_reason   = reason,
        )
