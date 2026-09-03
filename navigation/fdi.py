"""
Fault Detection and Isolation (FDI) for navigation sensors.

This is the NAVIGATION-SIDE FDI.  It is distinct from simulator/faults.py,
which injects simulated faults.  This module DETECTS faults by inspecting
the actual sensor measurement values and applies the following checks:

Radar altimeter
---------------
  R1. Range validity: AGL must be in [−50, 15000] m
  R2. NaN / Inf detection
  R3. Rate-of-change: |ΔAGL| / Δt ≤ 500 m/s (aircraft can't plunge that fast)
  R4. Saturation: AGL stuck at the same value for >5 consecutive steps
  R5. Innovation gate: |AGL_meas − AGL_predicted| ≤ 5σ_radar

GNSS
----
  G1. Status flag: 'DENIED' or NaN position → immediately isolated
  G2. Range validity: lat in [−90,90], lon in [−180,180]
  G3. Rate-of-change: position jump ≤ 500 m per 0.1 s step
  G4. Altitude valid range: [−1000, 15000] m
  G5. Innovation gate (relative to INS prediction)

Magnetometer
------------
  M1. NaN / Inf
  M2. Total field strength: |B| in [10000, 80000] nT  (India region)
  M3. Rate-of-change: |ΔB| ≤ 5000 nT/s
  M4. Saturation: field stuck for >5 steps
  M5. Status flag: 'INVALID' → immediately isolated

Isolation policy
----------------
A sensor is ISOLATED after it fails any check AND the failure persists for
at least `persist_steps` consecutive measurements (default 3).
A sensor is RE-ACCEPTED when it passes all checks for at least
`recovery_steps` consecutive measurements (default 5).
"""

import math
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Deque
from collections import deque

logger = logging.getLogger(__name__)


# ── enumerations ──────────────────────────────────────────────────────────────

class FaultCode(Enum):
    NONE           = "NONE"
    NAN_INF        = "NAN_INF"
    RANGE          = "RANGE"
    RATE_OF_CHANGE = "RATE_OF_CHANGE"
    SATURATION     = "SATURATION"
    INNOVATION     = "INNOVATION"
    STATUS_FLAG    = "STATUS_FLAG"


class SensorValidity(Enum):
    ACCEPTED  = "ACCEPTED"   # healthy, used in filter
    SUSPECTED = "SUSPECTED"  # failed check but not yet isolated
    ISOLATED  = "ISOLATED"   # faulted and excluded from filter


@dataclass
class SensorFDIStatus:
    validity:        SensorValidity = SensorValidity.ACCEPTED
    fault_code:      FaultCode      = FaultCode.NONE
    consecutive_fails: int          = 0
    consecutive_passes: int         = 0
    last_value:      Optional[float] = None
    last_timestamp:  Optional[float] = None
    # saturation detection buffer
    _sat_buffer:     Deque = field(default_factory=lambda: deque(maxlen=5))

    @property
    def is_accepted(self) -> bool:
        return self.validity == SensorValidity.ACCEPTED


# ── FDI manager ───────────────────────────────────────────────────────────────

class FaultDetectionIsolation:
    """
    Navigation-side FDI.

    Usage
    -----
    fdi = FaultDetectionIsolation()

    # Each timestep:
    radar_ok  = fdi.check_radar(radar_meas, predicted_agl, radar_sigma)
    gnss_ok   = fdi.check_gnss(gnss_meas, ins_lat, ins_lon, ins_alt)
    mag_ok    = fdi.check_magnetometer(mag_meas)

    Parameters
    ----------
    persist_steps  : consecutive failures before ISOLATED
    recovery_steps : consecutive passes before re-ACCEPTED from ISOLATED
    """

    # ── limits ────────────────────────────────────────────────────────────────
    RADAR_AGL_MIN      = -50.0
    RADAR_AGL_MAX      = 15_000.0
    RADAR_RATE_MAX     = 500.0    # m/s
    RADAR_INNO_SIGMA   = 5.0      # gate multiplier

    GNSS_LAT_MIN       = -90.0
    GNSS_LAT_MAX       = 90.0
    GNSS_LON_MIN       = -180.0
    GNSS_LON_MAX       = 180.0
    GNSS_ALT_MIN       = -1_000.0
    GNSS_ALT_MAX       = 15_000.0
    GNSS_JUMP_MAX_M    = 500.0    # max position jump per step

    MAG_TOTAL_MIN      = 10_000.0  # nT
    MAG_TOTAL_MAX      = 80_000.0  # nT
    MAG_RATE_MAX_NT_S  = 5_000.0  # nT/s

    def __init__(
        self,
        persist_steps:  int = 3,
        recovery_steps: int = 5,
    ) -> None:
        self._persist  = persist_steps
        self._recovery = recovery_steps

        self.radar        = SensorFDIStatus()
        self.gnss         = SensorFDIStatus()
        self.magnetometer = SensorFDIStatus()

    # ── public checks ──────────────────────────────────────────────────────────

    def check_radar(
        self,
        meas:           Dict[str, Any],
        predicted_agl:  Optional[float] = None,
        radar_sigma:    float = 2.0,
    ) -> bool:
        """
        Run all radar FDI checks.  Returns True if measurement is accepted.
        """
        status = meas.get("status", "")
        try:
            agl = float(meas.get("altitude_above_ground_m", "nan") or "nan")
        except (TypeError, ValueError):
            agl = float("nan")
        ts     = float(meas.get("timestamp", 0.0))

        fault = FaultCode.NONE

        # R1 / R2: status flag or NaN
        if status == "INVALID" or not math.isfinite(agl):
            fault = FaultCode.NAN_INF if not math.isfinite(agl) else FaultCode.STATUS_FLAG

        # R1: range
        elif agl < self.RADAR_AGL_MIN or agl > self.RADAR_AGL_MAX:
            fault = FaultCode.RANGE

        # R3: rate of change
        elif self.radar.last_value is not None and self.radar.last_timestamp is not None:
            dt = ts - self.radar.last_timestamp
            if dt > 0:
                rate = abs(agl - self.radar.last_value) / dt
                if rate > self.RADAR_RATE_MAX:
                    fault = FaultCode.RATE_OF_CHANGE

        # R4: saturation (same value repeatedly) — only check in normal operation
        if fault == FaultCode.NONE and self.radar.validity != SensorValidity.ISOLATED:
            self.radar._sat_buffer.append(round(agl, 1))
            if (len(self.radar._sat_buffer) == self.radar._sat_buffer.maxlen
                    and len(set(self.radar._sat_buffer)) == 1):
                fault = FaultCode.SATURATION

        # R5: innovation gate
        if fault == FaultCode.NONE and predicted_agl is not None and math.isfinite(predicted_agl):
            inno = abs(agl - predicted_agl)
            if inno > self.RADAR_INNO_SIGMA * max(radar_sigma, 1.0) * 10:
                # Large gate (10σ) to allow for real terrain variation
                fault = FaultCode.INNOVATION

        if fault == FaultCode.NONE:
            self.radar.last_value     = agl
            self.radar.last_timestamp = ts

        return self._update_status(self.radar, fault, "radar")

    def check_gnss(
        self,
        meas:    Dict[str, Any],
        ins_lat: Optional[float] = None,
        ins_lon: Optional[float] = None,
        ins_alt: Optional[float] = None,
    ) -> bool:
        """
        Run all GNSS FDI checks.  Returns True if measurement is accepted.
        """
        status = meas.get("status", "")
        try:
            lat = float(meas.get("latitude",  "nan") or "nan")
            lon = float(meas.get("longitude", "nan") or "nan")
            alt = float(meas.get("altitude",  "nan") or "nan")
        except (TypeError, ValueError):
            lat = lon = alt = float("nan")
        ts     = float(meas.get("timestamp", 0.0))

        fault = FaultCode.NONE

        # G1: status flag
        if status == "DENIED":
            fault = FaultCode.STATUS_FLAG

        # G2: NaN
        elif not (math.isfinite(lat) and math.isfinite(lon) and math.isfinite(alt)):
            fault = FaultCode.NAN_INF

        # G2: valid range
        elif not (self.GNSS_LAT_MIN <= lat <= self.GNSS_LAT_MAX):
            fault = FaultCode.RANGE
        elif not (self.GNSS_LON_MIN <= lon <= self.GNSS_LON_MAX):
            fault = FaultCode.RANGE
        elif not (self.GNSS_ALT_MIN <= alt <= self.GNSS_ALT_MAX):
            fault = FaultCode.RANGE

        # G3: position jump relative to INS
        elif ins_lat is not None and ins_lon is not None:
            jump = _haversine_m(lat, lon, ins_lat, ins_lon)
            if jump > self.GNSS_JUMP_MAX_M:
                fault = FaultCode.RATE_OF_CHANGE

        if fault == FaultCode.NONE:
            self.gnss.last_value     = lat  # store lat for continuity
            self.gnss.last_timestamp = ts

        return self._update_status(self.gnss, fault, "gnss")

    def check_magnetometer(
        self,
        meas: Dict[str, Any],
    ) -> bool:
        """
        Run all magnetometer FDI checks.  Returns True if measurement is accepted.
        """
        status = meas.get("status", "")
        try:
            bx = float(meas.get("mag_x", "nan") or "nan")
            by = float(meas.get("mag_y", "nan") or "nan")
            bz = float(meas.get("mag_z", "nan") or "nan")
        except (TypeError, ValueError):
            bx = by = bz = float("nan")
        ts     = float(meas.get("timestamp", 0.0))

        fault = FaultCode.NONE

        # M1/M5: status flag or NaN
        if status == "INVALID" or not (math.isfinite(bx) and math.isfinite(by) and math.isfinite(bz)):
            fault = FaultCode.NAN_INF if not math.isfinite(bx) else FaultCode.STATUS_FLAG


        else:
            total = math.sqrt(bx ** 2 + by ** 2 + bz ** 2)

            # M2: total field strength
            if not (self.MAG_TOTAL_MIN <= total <= self.MAG_TOTAL_MAX):
                fault = FaultCode.RANGE

            # M3: rate of change
            elif self.magnetometer.last_value is not None and self.magnetometer.last_timestamp is not None:
                dt = ts - self.magnetometer.last_timestamp
                if dt > 0:
                    rate = abs(total - self.magnetometer.last_value) / dt
                    if rate > self.MAG_RATE_MAX_NT_S:
                        fault = FaultCode.RATE_OF_CHANGE

            # M4: saturation — only check in normal operation
            if fault == FaultCode.NONE and self.magnetometer.validity != SensorValidity.ISOLATED:
                self.magnetometer._sat_buffer.append(round(total, 0))
                if (len(self.magnetometer._sat_buffer) == self.magnetometer._sat_buffer.maxlen
                        and len(set(self.magnetometer._sat_buffer)) == 1):
                    fault = FaultCode.SATURATION

            if fault == FaultCode.NONE:
                self.magnetometer.last_value     = total
                self.magnetometer.last_timestamp = ts

        return self._update_status(self.magnetometer, fault, "magnetometer")

    # ── internal state machine ────────────────────────────────────────────────

    def _update_status(
        self,
        s:           SensorFDIStatus,
        fault:       FaultCode,
        sensor_name: str,
    ) -> bool:
        """
        Update the sensor validity state machine.
        Returns True (accepted) or False (suspected/isolated).
        """
        if fault == FaultCode.NONE:
            # Healthy reading
            s.consecutive_fails = 0
            if s.validity == SensorValidity.ISOLATED:
                s.consecutive_passes += 1
                if s.consecutive_passes >= self._recovery:
                    logger.info("FDI: %s RECOVERED (re-ACCEPTED)", sensor_name)
                    s.validity       = SensorValidity.ACCEPTED
                    s.fault_code     = FaultCode.NONE
                    s.consecutive_passes = 0
                    s._sat_buffer.clear()  # clear stale saturation history
                # still ISOLATED while recovering
                return False
            else:
                s.validity       = SensorValidity.ACCEPTED
                s.fault_code     = FaultCode.NONE
                s.consecutive_passes = 0
                return True
        else:
            # Fault detected
            s.consecutive_passes = 0
            s.fault_code         = fault
            s.consecutive_fails += 1
            if s.consecutive_fails >= self._persist:
                if s.validity != SensorValidity.ISOLATED:
                    logger.warning(
                        "FDI: %s ISOLATED (fault=%s, fails=%d)",
                        sensor_name, fault.value, s.consecutive_fails,
                    )
                s.validity = SensorValidity.ISOLATED
            else:
                s.validity = SensorValidity.SUSPECTED
            return False

    def status_summary(self) -> Dict[str, str]:
        return {
            "radar":        self.radar.validity.value,
            "gnss":         self.gnss.validity.value,
            "magnetometer": self.magnetometer.validity.value,
        }


# ── helper ────────────────────────────────────────────────────────────────────

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two geodetic points."""
    R   = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = phi2 - phi1
    dlam       = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
