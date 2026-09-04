"""
Tests for INS propagation.
"""
import sys
import os
import math
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from navigation.ins import INSPropagator, INSState


def _make_imu(ts: float, ax=0.0, ay=0.0, az=-9.80665,
              rr=0.0, pr=0.0, yr=0.0):
    return {
        "timestamp": ts,
        "ax": ax, "ay": ay, "az": az,
        "roll_rate": rr, "pitch_rate": pr, "yaw_rate": yr,
    }


class TestINSPropagation(unittest.TestCase):

    def test_initial_state(self):
        """INS starts at given lat/lon/alt."""
        ins = INSPropagator(30.0, 78.0, 5000.0)
        s = ins.state
        self.assertAlmostEqual(s.latitude,  30.0)
        self.assertAlmostEqual(s.longitude, 78.0)
        self.assertAlmostEqual(s.altitude,  5000.0)

    def test_stationary_no_drift(self):
        """
        With zero accelerations and zero rates (gravity balanced):
        position should not significantly drift for 1 second.
        Note: gravity compensation keeps vertical mostly stable.
        """
        ins = INSPropagator(30.0, 78.0, 5000.0, initial_yaw=0.0)
        # Feed 10 steps of pure gravity-balanced IMU (az = -g, nothing else)
        for i in range(10):
            imu = _make_imu(i * 0.1, ax=0.0, ay=0.0, az=-9.80665)
            ins.propagate(imu)
        s = ins.state
        # Should stay close (within ~1 degree) to start
        self.assertAlmostEqual(s.latitude,  30.0, places=2)
        self.assertAlmostEqual(s.longitude, 78.0, places=2)

    def test_forward_motion(self):
        """Positive ax should move the aircraft in the heading direction."""
        ins = INSPropagator(30.0, 78.0, 5000.0, initial_yaw=0.0)  # heading N
        imu = _make_imu(0.1, ax=10.0)  # 10 m/s² forward (north)
        ins.propagate(imu)
        s = ins.state
        # After one step with a_n component, velocity should have increased
        # The position change depends on dt (0.1 s) — just check direction
        self.assertGreaterEqual(s.vel_north, 0.0)

    def test_gnss_denial_drift_grows(self):
        """
        With constant bias in accelerations, position error should grow over time
        (simulating INS-only drift in GNSS-denied mode).
        """
        ins = INSPropagator(30.0, 78.0, 5000.0, initial_yaw=0.0)
        # Add a small constant ax bias (0.05 m/s² ≈ typical IMU drift)
        for i in range(100):
            imu = _make_imu(i * 0.1, ax=0.05)  # 0.05 m/s² bias
            ins.propagate(imu)

        # After 10 seconds, drift should have accumulated
        self.assertGreater(ins.state.pos_drift_m, 0.0)

    def test_reset_position(self):
        """reset_position should update lat/lon/alt."""
        ins = INSPropagator(30.0, 78.0, 5000.0)
        ins.reset_position(31.0, 79.0, 4000.0)
        s = ins.state
        self.assertAlmostEqual(s.latitude,  31.0)
        self.assertAlmostEqual(s.longitude, 79.0)
        self.assertAlmostEqual(s.altitude,  4000.0)

    def test_position_property(self):
        """position property returns (lat, lon, alt) tuple."""
        ins = INSPropagator(25.0, 81.5, 2000.0)
        lat, lon, alt = ins.position
        self.assertAlmostEqual(lat, 25.0)
        self.assertAlmostEqual(lon, 81.5)
        self.assertAlmostEqual(alt, 2000.0)

    def test_mission_index_stored(self):
        """mission_index from propagate() is stored in state."""
        ins = INSPropagator(30.0, 78.0, 5000.0)
        imu = _make_imu(0.1)
        ins.propagate(imu, mission_index=42)
        self.assertEqual(ins.state.mission_index, 42)

    def test_full_reset(self):
        """reset_full should restore all state fields."""
        ins = INSPropagator(30.0, 78.0, 5000.0)
        # Dirty the state
        for i in range(5):
            ins.propagate(_make_imu(i * 0.1, ax=5.0))
        ins.reset_full(25.0, 81.5, 2000.0, yaw=1.0, vel_north=100.0, vel_east=50.0)
        s = ins.state
        self.assertAlmostEqual(s.latitude,   25.0)
        self.assertAlmostEqual(s.longitude,  81.5)
        self.assertAlmostEqual(s.altitude,   2000.0)
        self.assertAlmostEqual(s.yaw,        1.0)
        self.assertAlmostEqual(s.vel_north,  100.0)
        self.assertAlmostEqual(s.vel_east,   50.0)


if __name__ == "__main__":
    unittest.main()
