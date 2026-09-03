"""
Terrain Observability Analysis.

Computes how distinctive the local terrain is for navigation purposes.
High relief / large elevation variation → HIGH observability → TAN correction is trustworthy.
Low relief (flat plains, desert dunes) → LOW observability → TAN correction is downweighted.

Algorithm
---------
Given a grid of elevation samples centred on the current INS position:
1. Compute the standard deviation (relief proxy) of the elevation profile.
2. Compute the mean absolute gradient (slope proxy).
3. Combine into a single observability score.
4. Classify: LOW < MEDIUM < HIGH.

Thresholds are derived from expected SRTM statistics for the four terrain types:
  Mountain:      σ > 150 m              → HIGH
  Western Ghats: σ 30–150 m             → MEDIUM / HIGH
  Desert:        σ 5–30 m               → LOW / MEDIUM
  Flat Plain:    σ < 5 m                → LOW
"""

import math
import logging
from enum import Enum
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Classification thresholds (elevation std-dev in metres)
_STD_LOW_THRESHOLD    = 10.0   # below → LOW
_STD_HIGH_THRESHOLD   = 80.0   # above → HIGH
# Gradient thresholds (m per 100 m horizontal distance)
_GRAD_LOW_THRESHOLD   = 0.5
_GRAD_HIGH_THRESHOLD  = 5.0


class ObservabilityLevel(Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


class TerrainObservabilityResult:
    """Result of a terrain observability computation."""
    __slots__ = (
        "level", "elevation_std_m", "mean_abs_gradient",
        "profile_length", "score",
    )

    def __init__(
        self,
        level: ObservabilityLevel,
        elevation_std_m: float,
        mean_abs_gradient: float,
        profile_length: int,
        score: float,
    ) -> None:
        self.level             = level
        self.elevation_std_m   = elevation_std_m
        self.mean_abs_gradient = mean_abs_gradient
        self.profile_length    = profile_length
        self.score             = score          # 0.0 (flat) … 1.0 (very mountainous)

    def __repr__(self) -> str:
        return (
            f"TerrainObservabilityResult(level={self.level.value}, "
            f"std={self.elevation_std_m:.1f}m, "
            f"grad={self.mean_abs_gradient:.3f}, "
            f"score={self.score:.3f})"
        )


def compute_observability(
    elevations: List[float],
    spacing_m: float = 100.0,
) -> TerrainObservabilityResult:
    """
    Compute terrain observability from an elevation profile.

    Parameters
    ----------
    elevations  : list of terrain elevation samples (metres)
    spacing_m   : horizontal spacing between samples (metres)

    Returns
    -------
    TerrainObservabilityResult
    """
    n = len(elevations)
    if n < 2:
        return TerrainObservabilityResult(
            level=ObservabilityLevel.LOW,
            elevation_std_m=0.0,
            mean_abs_gradient=0.0,
            profile_length=n,
            score=0.0,
        )

    # --- Standard deviation of elevation ---
    mean_elev = sum(elevations) / n
    variance  = sum((e - mean_elev) ** 2 for e in elevations) / n
    std_elev  = math.sqrt(variance)

    # --- Mean absolute gradient ---
    gradients = [
        abs(elevations[i + 1] - elevations[i]) / spacing_m
        for i in range(n - 1)
    ]
    mean_grad = sum(gradients) / len(gradients)

    # --- Combined observability score (0–1) ---
    # Normalise each metric to [0,1] and take the geometric mean
    std_norm  = min(std_elev  / _STD_HIGH_THRESHOLD,  1.0)
    grad_norm = min(mean_grad / _GRAD_HIGH_THRESHOLD, 1.0)
    score     = math.sqrt(std_norm * grad_norm)  # geometric mean

    # --- Classification ---
    if std_elev < _STD_LOW_THRESHOLD and mean_grad < _GRAD_LOW_THRESHOLD:
        level = ObservabilityLevel.LOW
    elif std_elev >= _STD_HIGH_THRESHOLD or mean_grad >= _GRAD_HIGH_THRESHOLD:
        level = ObservabilityLevel.HIGH
    else:
        level = ObservabilityLevel.MEDIUM

    logger.debug(
        "Terrain obs: std=%.1fm grad=%.3f score=%.3f → %s",
        std_elev, mean_grad, score, level.value,
    )

    return TerrainObservabilityResult(
        level=level,
        elevation_std_m=std_elev,
        mean_abs_gradient=mean_grad,
        profile_length=n,
        score=score,
    )


def sample_elevation_profile_around(
    terrain_provider,
    lat: float,
    lon: float,
    radius_m: float = 2000.0,
    n_points: int = 21,
) -> Tuple[List[float], float]:
    """
    Sample a terrain profile centred on (lat, lon) along the N–S and E–W
    cross-sections and return combined unique elevations plus actual spacing.

    Parameters
    ----------
    terrain_provider : SRTMTerrainProvider (or any get_elevation callable)
    lat, lon         : centre position
    radius_m         : half-width of the sampling window in metres
    n_points         : number of sample points along each transect

    Returns
    -------
    elevations : list[float]   terrain elevation samples
    spacing_m  : float         approximate spacing between consecutive samples
    """
    R = 6_371_000.0
    # Degrees per metre
    dlat_per_m = 1.0 / (math.pi / 180.0 * R)
    dlon_per_m = 1.0 / (math.pi / 180.0 * R * math.cos(math.radians(lat)))

    step_m   = 2 * radius_m / (n_points - 1) if n_points > 1 else radius_m
    step_lat = step_m * dlat_per_m
    step_lon = step_m * dlon_per_m

    elevations = []
    # N-S transect
    for i in range(n_points):
        sample_lat = lat - radius_m * dlat_per_m + i * step_lat
        elev = terrain_provider.get_elevation(sample_lat, lon)
        elevations.append(elev)
    # E-W transect (skip centre to avoid double-counting)
    for i in range(n_points):
        if i == n_points // 2:
            continue
        sample_lon = lon - radius_m * dlon_per_m + i * step_lon
        elev = terrain_provider.get_elevation(lat, sample_lon)
        elevations.append(elev)

    return elevations, step_m
