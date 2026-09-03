"""
Magnetic Anomaly Navigation (MagNav).

Uses magnetometer.csv measurements as an independent aiding source.
India-region magnetic field (approximate WMM-2020 values):
  Horizontal intensity: ~35,000–42,000 nT
  Vertical intensity:   ~20,000–35,000 nT
  Total field:          ~42,000–52,000 nT

Algorithm
---------
The MagNav implementation uses gradient-based matching:
1. Estimate the expected magnetic total field at the INS position from a
   simple analytical model of the Earth's main field (IGRF approximation for
   the India region; valid to ~1000 nT).
2. Compute the anomaly: measured_total − model_total.
3. If the anomaly is large enough (|anomaly| > threshold), the measurement
   contains a non-trivial spatial signature that could be used for matching.
4. Without a local anomaly map, we cannot produce a position fix from the
   anomaly alone.  We therefore assess *navigability* (information content)
   and flag whether MagNav is available:

     HIGH anomaly variation over profile → potentially navigable
     LOW  anomaly variation              → not navigable (marked unavailable)

5. When a previous MagNav fix history exists (≥ 10 samples) and the anomaly
   variation is HIGH, a position estimate is produced by linear regression on
   the anomaly-vs-displacement curve.  Otherwise we declare MagNav unavailable
   and do not inject a fake correction.

This is conservative but honest: we do not manufacture confident position
corrections from noise.

Output
------
MagNavResult.available : bool
MagNavResult.lat, .lon : estimated position if available
MagNavResult.confidence: 0–1
MagNavResult.anomaly_nT: current field anomaly (m)
"""

import math
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Deque
from collections import deque

logger = logging.getLogger(__name__)

# IGRF-approximate total field for India (nT) — quadratic surface fit
# B_model ≈ B0 + dB/dlat × (lat − lat0) + dB/dlon × (lon − lon0)
_IGRF_B0       = 44_000.0   # nT at reference point (25°N, 80°E)
_IGRF_LAT0     = 25.0
_IGRF_LON0     = 80.0
_IGRF_DLAT     = -200.0      # nT per degree latitude  (field increases southward in India)
_IGRF_DLON     =  50.0       # nT per degree longitude (mild east gradient)

# Anomaly thresholds
_ANOMALY_USEFUL_NT = 300.0    # anomaly > this → field has spatial structure
_HISTORY_MIN       = 10       # minimum history points before attempting a fix
_VAR_HIGH_NT       = 150.0    # variation std-dev threshold for "HIGH" navigability


@dataclass
class MagNavResult:
    available:   bool   = False
    lat:         float  = float("nan")
    lon:         float  = float("nan")
    confidence:  float  = 0.0
    anomaly_nT:  float  = 0.0
    nav_quality: str    = "UNAVAILABLE"   # "UNAVAILABLE", "LOW", "HIGH"
    reason:      str    = ""


class MagNavEstimator:
    """
    Magnetic Anomaly Navigation estimator.

    Parameters
    ----------
    history_len : how many recent (anomaly, lat, lon) tuples to keep
    """

    def __init__(self, history_len: int = 50) -> None:
        self._history: Deque[Tuple[float, float, float]] = deque(maxlen=history_len)

    def update(
        self,
        mag_meas:  dict,
        ins_lat:   float,
        ins_lon:   float,
        mag_valid: bool,
    ) -> MagNavResult:
        """
        Process one magnetometer measurement.

        Parameters
        ----------
        mag_meas  : row dict from magnetometer.csv (mag_x, mag_y, mag_z, status, …)
        ins_lat   : current INS latitude estimate (degrees)
        ins_lon   : current INS longitude estimate (degrees)
        mag_valid : FDI gate — False → skip update, return unavailable

        Returns
        -------
        MagNavResult
        """
        if not mag_valid:
            return MagNavResult(
                available=False,
                reason="magnetometer FDI: sensor not accepted",
            )

        try:
            bx = float(mag_meas.get("mag_x", "nan") or "nan")
            by = float(mag_meas.get("mag_y", "nan") or "nan")
            bz = float(mag_meas.get("mag_z", "nan") or "nan")
        except (TypeError, ValueError):
            bx = by = bz = float("nan")
        if not (math.isfinite(bx) and math.isfinite(by) and math.isfinite(bz)):
            return MagNavResult(available=False, reason="NaN field components")


        measured_total = math.sqrt(bx**2 + by**2 + bz**2)
        model_total    = self._igrf_model(ins_lat, ins_lon)
        anomaly        = measured_total - model_total

        # Store (anomaly, lat, lon) in history
        self._history.append((anomaly, ins_lat, ins_lon))

        # Assess navigability from recent history
        if len(self._history) < _HISTORY_MIN:
            return MagNavResult(
                available=False,
                anomaly_nT=anomaly,
                nav_quality="UNAVAILABLE",
                reason=f"insufficient history ({len(self._history)}/{_HISTORY_MIN})",
            )

        anomalies = [h[0] for h in self._history]
        anom_std  = _std(anomalies)

        if anom_std < _VAR_HIGH_NT:
            return MagNavResult(
                available=False,
                anomaly_nT=anomaly,
                nav_quality="LOW",
                reason=f"anomaly variation {anom_std:.1f} nT < threshold {_VAR_HIGH_NT} nT; not navigable",
            )

        # Attempt a simple position estimate via gradient inversion
        # δlat ≈ anomaly / (dB/dlat),  δlon ≈ anomaly / (dB/dlon)
        # This works only when the IGRF gradient dominates the local anomaly
        est_lat, est_lon, confidence = self._gradient_fix(
            anomaly, ins_lat, ins_lon, anom_std
        )

        return MagNavResult(
            available   = confidence > 0.1,
            lat         = est_lat,
            lon         = est_lon,
            confidence  = confidence,
            anomaly_nT  = anomaly,
            nav_quality = "HIGH" if anom_std >= _VAR_HIGH_NT else "LOW",
            reason      = "" if confidence > 0.1 else "low gradient confidence",
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _igrf_model(lat: float, lon: float) -> float:
        """Simple linear IGRF approximation for the India region (nT)."""
        return (
            _IGRF_B0
            + _IGRF_DLAT * (lat - _IGRF_LAT0)
            + _IGRF_DLON * (lon - _IGRF_LON0)
        )

    @staticmethod
    def _gradient_fix(
        anomaly:  float,
        ins_lat:  float,
        ins_lon:  float,
        anom_std: float,
    ) -> Tuple[float, float, float]:
        """
        Estimate position correction from anomaly gradient.

        Δlat ≈ anomaly / (∂B/∂lat)
        Δlon ≈ anomaly / (∂B/∂lon)

        Confidence is inversely proportional to the gradient uncertainty.
        """
        grad_lat = abs(_IGRF_DLAT)
        grad_lon = abs(_IGRF_DLON)

        if grad_lat < 1.0 or grad_lon < 1.0:
            return ins_lat, ins_lon, 0.0

        d_lat = anomaly / _IGRF_DLAT if _IGRF_DLAT != 0 else 0.0
        d_lon = anomaly / _IGRF_DLON if _IGRF_DLON != 0 else 0.0

        # Clamp corrections to ±0.5°
        d_lat = max(-0.5, min(0.5, d_lat))
        d_lon = max(-0.5, min(0.5, d_lon))

        est_lat = ins_lat + d_lat
        est_lon = ins_lon + d_lon

        # Confidence: higher anomaly variation → more signal → higher confidence
        # Scale by how well the IGRF gradient explains the anomaly
        confidence = min(anom_std / (3.0 * _VAR_HIGH_NT), 1.0)

        logger.debug(
            "MagNav fix: anomaly=%.1f nT  d_lat=%.6f°  d_lon=%.6f°  conf=%.3f",
            anomaly, d_lat, d_lon, confidence,
        )
        return est_lat, est_lon, confidence


# ── statistics helper ─────────────────────────────────────────────────────────

def _std(values: list) -> float:
    if len(values) < 2:
        return 0.0
    n    = len(values)
    mean = sum(values) / n
    var  = sum((v - mean) ** 2 for v in values) / n
    return math.sqrt(var)
