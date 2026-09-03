"""
Inertial Navigation System (INS) propagation.

Reads IMU measurements (ax, ay, az, roll_rate, pitch_rate, yaw_rate) and
integrates them to maintain an estimated position, velocity, and attitude.

Key properties
--------------
* Does NOT use trajectory.csv latitude/longitude for correction.
* When GNSS is available, the INS state is optionally reset/corrected by the
  EKF (passed in from outside — the INS itself stays pure dead-reckoning).
* When GNSS is denied, position error grows monotonically from IMU biases and
  noise accumulation (realistic INS drift behaviour).

State vector (local-level NED frame)
-------------------------------------
  pos_north_m   northward position offset from reference point (m)
  pos_east_m    eastward  position offset from reference point (m)
  pos_down_m    downward  position offset (≈ –altitude change in m)
  vel_north     northward velocity (m/s)
  vel_east      eastward  velocity (m/s)
  vel_down      downward  velocity (m/s)
  roll          roll angle  (rad)
  pitch         pitch angle (rad)
  yaw           yaw  angle  (rad)

Position in geodetic (lat, lon, alt) is derived from the NED offset via a
flat-Earth approximation (valid for the mission extents of a few tens of km).
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# WGS-84 equatorial radius
_R_EARTH = 6_371_000.0


@dataclass
class INSState:
    """Current INS estimate."""
    # ─── position ─────────────────────────────────────────────────────────────
    latitude:    float = 0.0   # degrees
    longitude:   float = 0.0   # degrees
    altitude:    float = 0.0   # metres (WGS-84 ellipsoidal / barometric)
    # ─── velocity (NED) ───────────────────────────────────────────────────────
    vel_north:   float = 0.0   # m/s
    vel_east:    float = 0.0   # m/s
    vel_down:    float = 0.0   # m/s
    # ─── attitude ─────────────────────────────────────────────────────────────
    roll:        float = 0.0   # rad
    pitch:       float = 0.0   # rad
    yaw:         float = 0.0   # rad
    # ─── timing ───────────────────────────────────────────────────────────────
    timestamp:   float = 0.0   # seconds
    mission_index: int = 0
    # ─── accumulated drift diagnostics ────────────────────────────────────────
    pos_drift_m: float = 0.0   # rough cumulative |Δpos| since last reset (m)


class INSPropagator:
    """
    Flat-Earth strapdown INS mechanisation.

    The IMU body-frame accelerations are rotated into NED using the current
    attitude angles, gravity is removed, then integrated twice to get position.
    Angular rates are integrated to update attitude.

    Parameters
    ----------
    initial_lat  : reference latitude  (degrees)
    initial_lon  : reference longitude (degrees)
    initial_alt  : reference altitude  (metres)
    initial_yaw  : initial heading     (radians)
    """

    GRAVITY = 9.80665  # m/s²

    def __init__(
        self,
        initial_lat: float,
        initial_lon: float,
        initial_alt: float,
        initial_yaw: float = 0.0,
    ) -> None:
        self.state = INSState(
            latitude=initial_lat,
            longitude=initial_lon,
            altitude=initial_alt,
            yaw=initial_yaw,
        )
        self._ref_lat = initial_lat
        self._ref_lon = initial_lon
        self._ref_alt = initial_alt
        # Metres per degree (flat-Earth, evaluated at reference latitude)
        self._m_per_deg_lat = math.pi / 180.0 * _R_EARTH
        self._m_per_deg_lon = math.pi / 180.0 * _R_EARTH * math.cos(
            math.radians(initial_lat)
        )
        self._prev_timestamp: Optional[float] = None

    # ── public interface ──────────────────────────────────────────────────────

    def propagate(
        self,
        imu_meas: Dict[str, Any],
        mission_index: int = 0,
    ) -> INSState:
        """
        Propagate the INS state forward by one IMU measurement.

        Parameters
        ----------
        imu_meas     : dict from imu.csv row (timestamp, ax, ay, az,
                       roll_rate, pitch_rate, yaw_rate)
        mission_index: current mission step index

        Returns
        -------
        INSState : updated state (same object, also returned for convenience)
        """
        t   = float(imu_meas["timestamp"])
        ax  = float(imu_meas["ax"])
        ay  = float(imu_meas["ay"])
        az  = float(imu_meas["az"])
        rr  = float(imu_meas["roll_rate"])
        pr  = float(imu_meas["pitch_rate"])
        yr  = float(imu_meas["yaw_rate"])

        if self._prev_timestamp is None:
            dt = 0.1
        else:
            dt = t - self._prev_timestamp
            if dt <= 0 or dt > 1.0:
                dt = 0.1
        self._prev_timestamp = t

        s = self.state

        # ── 1. Update attitude (Euler integration of body rates) ──────────────
        s.roll  += rr * dt
        s.pitch += pr * dt
        s.yaw   += yr * dt
        # Normalise yaw to [−π, π]
        s.yaw = _wrap_angle(s.yaw)

        # ── 2. Rotate body-frame specific force into NED ──────────────────────
        # Using simple 3-2-1 (yaw-pitch-roll) rotation
        cr, sr = math.cos(s.roll),  math.sin(s.roll)
        cp, sp = math.cos(s.pitch), math.sin(s.pitch)
        cy, sy = math.cos(s.yaw),   math.sin(s.yaw)

        # Body → NED rotation matrix rows
        # f_ned = R_body2ned @ [ax, ay, az]^T
        f_n = (cy * cp) * ax + (cy * sp * sr - sy * cr) * ay + (cy * sp * cr + sy * sr) * az
        f_e = (sy * cp) * ax + (sy * sp * sr + cy * cr) * ay + (sy * sp * cr - cy * sr) * az
        f_d = (-sp)      * ax + (cp * sr)               * ay + (cp * cr)               * az

        # ── 3. Remove gravity (NED: gravity acts in +Down direction) ──────────
        a_n = f_n                          # no gravity in North
        a_e = f_e                          # no gravity in East
        a_d = f_d + self.GRAVITY           # gravity = +9.81 m/s² Down

        # ── 4. Integrate accelerations → velocity ──────────────────────────────
        s.vel_north += a_n * dt
        s.vel_east  += a_e * dt
        s.vel_down  += a_d * dt

        # ── 5. Integrate velocity → position ─────────────────────────────────
        d_north = s.vel_north * dt   # metres
        d_east  = s.vel_east  * dt
        d_down  = s.vel_down  * dt

        s.latitude  += d_north / self._m_per_deg_lat
        s.longitude += d_east  / self._m_per_deg_lon
        s.altitude  -= d_down                         # positive alt = up; +down = lower alt

        # ── 6. Update diagnostics ─────────────────────────────────────────────
        s.pos_drift_m += math.sqrt(d_north ** 2 + d_east ** 2)
        s.timestamp    = t
        s.mission_index = mission_index

        return s

    def reset_position(
        self,
        lat: float,
        lon: float,
        alt: float,
    ) -> None:
        """
        Reset the INS position (e.g., after EKF correction).
        Does NOT reset velocity or attitude — only position.
        """
        self.state.latitude  = lat
        self.state.longitude = lon
        self.state.altitude  = alt
        self.state.pos_drift_m = 0.0
        # Re-anchor flat-Earth reference
        self._ref_lat = lat
        self._ref_lon = lon
        self._m_per_deg_lat = math.pi / 180.0 * _R_EARTH
        self._m_per_deg_lon = math.pi / 180.0 * _R_EARTH * math.cos(
            math.radians(lat)
        )

    def reset_full(
        self,
        lat: float,
        lon: float,
        alt: float,
        yaw: float = 0.0,
        vel_north: float = 0.0,
        vel_east:  float = 0.0,
    ) -> None:
        """Full state reset (used at mission start)."""
        self.state = INSState(
            latitude=lat, longitude=lon, altitude=alt, yaw=yaw,
            vel_north=vel_north, vel_east=vel_east,
        )
        self._ref_lat = lat
        self._ref_lon = lon
        self._ref_alt = alt
        self._m_per_deg_lat = math.pi / 180.0 * _R_EARTH
        self._m_per_deg_lon = math.pi / 180.0 * _R_EARTH * math.cos(
            math.radians(lat)
        )
        self._prev_timestamp = None

    @property
    def position(self) -> Tuple[float, float, float]:
        """Current (lat, lon, alt) tuple."""
        s = self.state
        return s.latitude, s.longitude, s.altitude


# ── helpers ───────────────────────────────────────────────────────────────────

def _wrap_angle(angle: float) -> float:
    """Wrap angle to [−π, π]."""
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle
