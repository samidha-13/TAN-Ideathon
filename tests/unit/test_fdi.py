"""
Tests for FDI (Fault Detection and Isolation).
"""
import sys
import os
import math
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from navigation.fdi import FaultDetectionIsolation, SensorValidity, FaultCode


def _radar_meas(ts=0.0, agl=900.0, status="VALID"):
    return {"timestamp": ts, "altitude_above_ground_m": agl, "status": status}

def _gnss_meas(ts=0.0, lat=30.0, lon=78.0, alt=5000.0, status="AVAILABLE"):
    return {"timestamp": ts, "latitude": lat, "longitude": lon,
            "altitude": alt, "velocity": 200.0, "status": status}

def _mag_meas(ts=0.0, bx=30000.0, by=1000.0, bz=40000.0, status="VALID"):
    return {"timestamp": ts, "mag_x": bx, "mag_y": by, "mag_z": bz, "status": status}


class TestFDIRadar(unittest.TestCase):

    def setUp(self):
        self.fdi = FaultDetectionIsolation(persist_steps=3, recovery_steps=5)

    def test_healthy_radar_accepted(self):
        result = self.fdi.check_radar(_radar_meas(agl=900.0))
        self.assertTrue(result)
        self.assertEqual(self.fdi.radar.validity, SensorValidity.ACCEPTED)

    def test_invalid_status_isolates_after_persist(self):
        """INVALID status flag should isolate after persist_steps."""
        for i in range(5):
            r = self.fdi.check_radar(_radar_meas(ts=i*0.1, agl=float("nan"), status="INVALID"))
        self.assertEqual(self.fdi.radar.validity, SensorValidity.ISOLATED)
        self.assertFalse(r)

    def test_nan_agl_isolates(self):
        for i in range(5):
            self.fdi.check_radar(_radar_meas(agl=float("nan"), status="VALID"))
        self.assertEqual(self.fdi.radar.validity, SensorValidity.ISOLATED)

    def test_out_of_range_agl_isolates(self):
        for i in range(5):
            self.fdi.check_radar(_radar_meas(agl=-9999.0))
        self.assertNotEqual(self.fdi.radar.validity, SensorValidity.ACCEPTED)

    def test_rate_of_change_fault(self):
        """Sudden jump in AGL (>500 m/s) should trigger rate-of-change fault."""
        self.fdi.check_radar(_radar_meas(ts=0.0, agl=900.0))
        # Next reading: 1000 m change in 0.1 s → 10000 m/s rate
        for i in range(5):
            self.fdi.check_radar(_radar_meas(ts=(i+1)*0.1, agl=900.0 + 1000.0))
        self.assertNotEqual(self.fdi.radar.validity, SensorValidity.ACCEPTED)

    def test_recovery_after_fault(self):
        """After recovery_steps of healthy readings, sensor is re-accepted."""
        # Inject fault
        for i in range(5):
            self.fdi.check_radar(_radar_meas(agl=float("nan"), status="INVALID"))
        self.assertEqual(self.fdi.radar.validity, SensorValidity.ISOLATED)
        # Feed healthy readings with slightly varying values (to avoid saturation check)
        for i in range(recovery_steps := 7):
            self.fdi.check_radar(_radar_meas(ts=i*0.1, agl=900.0 + i, status="VALID"))
        self.assertEqual(self.fdi.radar.validity, SensorValidity.ACCEPTED)



class TestFDIGNSS(unittest.TestCase):

    def setUp(self):
        self.fdi = FaultDetectionIsolation(persist_steps=3, recovery_steps=5)

    def test_healthy_gnss_accepted(self):
        result = self.fdi.check_gnss(_gnss_meas())
        self.assertTrue(result)

    def test_denied_status_isolates(self):
        for i in range(5):
            self.fdi.check_gnss(_gnss_meas(status="DENIED", lat=float("nan"),
                                            lon=float("nan"), alt=float("nan")))
        self.assertEqual(self.fdi.gnss.validity, SensorValidity.ISOLATED)

    def test_nan_position_fault(self):
        for i in range(5):
            self.fdi.check_gnss(_gnss_meas(lat=float("nan")))
        self.assertNotEqual(self.fdi.gnss.validity, SensorValidity.ACCEPTED)

    def test_out_of_range_lat(self):
        for i in range(5):
            self.fdi.check_gnss(_gnss_meas(lat=999.0))
        self.assertNotEqual(self.fdi.gnss.validity, SensorValidity.ACCEPTED)

    def test_innovation_jump(self):
        """Large jump from INS position should flag as fault."""
        for i in range(5):
            self.fdi.check_gnss(
                _gnss_meas(lat=35.0, lon=85.0),  # far from INS at (30,78)
                ins_lat=30.0, ins_lon=78.0, ins_alt=5000.0,
            )
        self.assertNotEqual(self.fdi.gnss.validity, SensorValidity.ACCEPTED)


class TestFDIMagnetometer(unittest.TestCase):

    def setUp(self):
        self.fdi = FaultDetectionIsolation(persist_steps=3, recovery_steps=5)

    def test_healthy_mag_accepted(self):
        result = self.fdi.check_magnetometer(_mag_meas())
        self.assertTrue(result)

    def test_invalid_status_isolates(self):
        for i in range(5):
            self.fdi.check_magnetometer(
                _mag_meas(bx=float("nan"), by=float("nan"), bz=float("nan"), status="INVALID")
            )
        self.assertEqual(self.fdi.magnetometer.validity, SensorValidity.ISOLATED)

    def test_weak_total_field_fault(self):
        """Total field < 10000 nT → range fault."""
        for i in range(5):
            self.fdi.check_magnetometer(_mag_meas(bx=100.0, by=100.0, bz=100.0))
        self.assertNotEqual(self.fdi.magnetometer.validity, SensorValidity.ACCEPTED)

    def test_status_summary(self):
        """status_summary returns dict with correct keys."""
        s = self.fdi.status_summary()
        self.assertIn("radar", s)
        self.assertIn("gnss", s)
        self.assertIn("magnetometer", s)


if __name__ == "__main__":
    unittest.main()
