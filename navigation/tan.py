"""
Terrain-Aided Navigation (TAN) module.

Algorithm: terrain-profile matching via Normalized Cross-Correlation (NCC).

Given:
  - INS predicted positions over a recent time window
  - Radar altimeter AGL measurements over the same window
  - SRTM terrain database

Workflow
--------
1. Build observed terrain profile from radar AGL + INS altitude:
       observed[i] = INS_alt[i] − radar_AGL[i]
2. Generate candidate position offsets around the current INS estimate.
3. For each candidate, extract a DEM terrain profile along the INS path
   shifted by the candidate offset.
4. Compute NCC between observed and candidate profiles.
5. Best-matching candidate → TAN position measurement fed to EKF.

The TAN module does NOT receive the ground-truth trajectory.
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
_DEFAULT_SEARCH_RADIUS_M = 3_000.0
_DEFAULT_GRID_STEPS      = 11
_MIN_AGL_M               = -50.0
_MAX_AGL_M               = 15_000.0
_MIN_PROFILE_LEN         = 10
# NCC thresholds by observability level (higher bar on ambiguous terrain)
_MIN_NCC_HIGH            = 0.70
_MIN_NCC_MEDIUM          = 0.85


@dataclass
class ProfileSample:
    """One INS position paired with a radar AGL reading."""
    ins_lat:   float
    ins_lon:   float
    ins_alt:   float
    radar_agl: float


@dataclass
class TANResult:
    """Result of one TAN measurement computation."""
    valid:            bool
    estimated_lat:    float
    estimated_lon:    float
    match_score:      float          # NCC in [0, 1]
    residual_m:       float          # mean |obs − cand| at best match (m)
    search_radius_m:  float
    n_candidates:     int
    terrain_obs:      Optional[TerrainObservabilityResult] = None
    reject_reason:    str = ""


def normalized_cross_correlation(obs: List[float], cand: List[float]) -> float:
    """
    Compute NCC between two equal-length profiles.

    Returns a value in [-1, 1].  Profiles are mean-centred before correlation.
    """
    n = len(obs)
    if n < 2 or n != len(cand):
        return 0.0

    mean_o = sum(obs) / n
    mean_c = sum(cand) / n
    a = [obs[i] - mean_o for i in range(n)]
    b = [cand[i] - mean_c for i in range(n)]

    num   = sum(a[i] * b[i] for i in range(n))
    denom = math.sqrt(sum(x * x for x in a) * sum(x * x for x in b))
    if denom < 1e-9:
        return 0.0
    return num / denom


def _mean_abs_diff(obs: List[float], cand: List[float]) -> float:
    n = len(obs)
    if n == 0:
        return float("inf")
    return sum(abs(obs[i] - cand[i]) for i in range(n)) / n


class TerrainAidedNavigation:
    """
    Terrain-Aided Navigation using SRTM DEM + radar altimeter profile matching.
    """

    def __init__(
        self,
        terrain_provider,
        search_radius_m: float = _DEFAULT_SEARCH_RADIUS_M,
        grid_steps: int = _DEFAULT_GRID_STEPS,
        min_profile_len: int = _MIN_PROFILE_LEN,
    ) -> None:
        self._terrain          = terrain_provider
        self._radius           = search_radius_m
        self._grid_steps       = grid_steps
        self._min_profile_len  = min_profile_len
        self._R                = 6_371_000.0

    def compute(
        self,
        ins_lat:     float,
        ins_lon:     float,
        ins_alt:     float,
        profile:     List[ProfileSample],
        obs_result:  Optional[TerrainObservabilityResult] = None,
        search_radius_m: Optional[float] = None,
    ) -> TANResult:
        """
        Compute a TAN position measurement from a radar terrain profile.

        Parameters
        ----------
        ins_lat, ins_lon, ins_alt : current INS position
        profile                   : recent (INS, radar) sample pairs
        obs_result                : pre-computed terrain observability (optional)
        """
        # ── 0. Profile length gate ────────────────────────────────────────────
        if len(profile) < self._min_profile_len:
            return self._reject(
                f"insufficient profile length ({len(profile)} < {self._min_profile_len})"
            )

        # Validate radar readings in profile
        observed: List[float] = []
        path: List[Tuple[float, float]] = []
        for sample in profile:
            agl = sample.radar_agl
            if not math.isfinite(agl):
                return self._reject("radar profile contains NaN/Inf")
            if agl < _MIN_AGL_M or agl > _MAX_AGL_M:
                return self._reject(f"radar_agl={agl:.1f} m out of valid range")
            observed.append(sample.ins_alt - agl)
            path.append((sample.ins_lat, sample.ins_lon))

        # ── 1. Terrain observability ──────────────────────────────────────────
        radius = search_radius_m if search_radius_m is not None else self._radius
        # Bound radius between 50m and self._radius
        radius = max(50.0, min(radius, self._radius))

        if obs_result is None:
            elevs, spacing = sample_elevation_profile_around(
                self._terrain, ins_lat, ins_lon,
                radius_m=radius, n_points=self._grid_steps,
            )
            obs_result = compute_observability(elevs, spacing)

        if obs_result.level == ObservabilityLevel.LOW:
            min_ncc = 0.90
        elif obs_result.level == ObservabilityLevel.MEDIUM:
            min_ncc = _MIN_NCC_MEDIUM
        else:
            min_ncc = _MIN_NCC_HIGH

        # ── 2. Candidate grid around current INS ─────────────────────────────
        candidates = self._build_grid_dynamic(ins_lat, ins_lon, radius)
        if not candidates:
            return self._reject("candidate grid is empty")

        # ── 3. NCC scoring ────────────────────────────────────────────────────
        best_ncc    = -2.0
        best_lat    = ins_lat
        best_lon    = ins_lon
        best_resid  = float("inf")

        for (c_lat, c_lon) in candidates:
            d_lat = c_lat - ins_lat
            d_lon = c_lon - ins_lon
            candidate = [
                self._terrain.get_elevation(p_lat + d_lat, p_lon + d_lon)
                for p_lat, p_lon in path
            ]
            ncc   = normalized_cross_correlation(observed, candidate)
            resid = _mean_abs_diff(observed, candidate)

            if ncc > best_ncc:
                best_ncc   = ncc
                best_lat   = c_lat
                best_lon   = c_lon
                best_resid = resid

        # Map NCC from [-1, 1] to [0, 1] for downstream consumers
        match_score = max(0.0, best_ncc)

        # ── 4. Quality gate ───────────────────────────────────────────────────
        if best_ncc < min_ncc:
            return self._reject(
                f"NCC {best_ncc:.4f} below threshold {min_ncc:.2f} "
                f"(obs={obs_result.level.value})",
                obs=obs_result,
            )

        logger.debug(
            "TAN NCC match: best=(%.6f, %.6f) ncc=%.4f resid=%.2fm obs=%s",
            best_lat, best_lon, best_ncc, best_resid, obs_result.level.value,
        )

        return TANResult(
            valid           = True,
            estimated_lat   = best_lat,
            estimated_lon   = best_lon,
            match_score     = match_score,
            residual_m      = best_resid,
            search_radius_m = radius,
            n_candidates    = len(candidates),
            terrain_obs     = obs_result,
        )

    def _build_grid_dynamic(
        self, centre_lat: float, centre_lon: float, radius: float
    ) -> List[Tuple[float, float]]:
        m_per_deg_lat = math.pi / 180.0 * self._R
        m_per_deg_lon = math.pi / 180.0 * self._R * math.cos(
            math.radians(centre_lat)
        )
        if m_per_deg_lat == 0 or m_per_deg_lon == 0:
            return []

        step = (2 * radius) / (self._grid_steps - 1) if self._grid_steps > 1 else radius
        half = radius

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
    def _reject(
        reason: str,
        obs: Optional[TerrainObservabilityResult] = None,
    ) -> TANResult:
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
