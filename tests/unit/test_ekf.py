"""
Tests for EKF (Extended Kalman Filter) navigation filter.
"""
import sys
import os
import math
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from navigation.ekf import NavigationEKF


class TestEKFPredict(unittest.TestCase):

    def test_covariance_grows_on_predict(self):
        """EKF covariance should grow with each predict step (process noise)."""
        ekf = NavigationEKF(q_pos_deg=1e-5, q_vel=0.1, q_att=1e-3)
        initial_cov = ekf.get_covariance_diagonal()[:]
        for _ in range(10):
            ekf.predict(dt=0.1)
        final_cov = ekf.get_covariance_diagonal()
        # Diagonal must have grown
        for i in range(9):
            self.assertGreaterEqual(
                final_cov[i], initial_cov[i],
                f"Covariance[{i}] did not grow: {initial_cov[i]} → {final_cov[i]}",
            )

    def test_initial_correction_zero(self):
        """Initial error state should be zero."""
        ekf = NavigationEKF()
        corr = ekf.get_correction()
        self.assertEqual(len(corr), 9)
        for v in corr:
            self.assertAlmostEqual(v, 0.0)


class TestEKFGNSSUpdate(unittest.TestCase):

    def test_gnss_update_reduces_error(self):
        """GNSS update should pull correction towards the observation."""
        ekf = NavigationEKF(q_pos_deg=1e-6)
        ekf.predict()
        # INS thinks 30.0°, GNSS says 30.001° → correction should be ~0.001°
        ekf.update_gnss(
            ins_lat=30.0, ins_lon=78.0, ins_alt=5000.0,
            gnss_lat=30.001, gnss_lon=78.001, gnss_alt=5010.0,
        )
        corr = ekf.get_correction()
        # Correction should be non-zero in lat/lon/alt direction
        self.assertNotAlmostEqual(corr[0], 0.0, places=8)
        self.assertNotAlmostEqual(corr[1], 0.0, places=8)

    def test_gnss_apply_correction(self):
        """apply_correction_to_ins should return corrected position."""
        ekf = NavigationEKF(q_pos_deg=1e-6)
        ekf.predict()
        ekf.update_gnss(
            ins_lat=30.0, ins_lon=78.0, ins_alt=5000.0,
            gnss_lat=30.01, gnss_lon=78.01, gnss_alt=5100.0,
        )
        c_lat, c_lon, c_alt = ekf.apply_correction_to_ins(30.0, 78.0, 5000.0)
        # Corrected position should be shifted towards GNSS observation
        self.assertGreater(c_lat, 30.0)
        self.assertGreater(c_lon, 78.0)

    def test_gnss_update_decreases_uncertainty(self):
        """After a GNSS update, position uncertainty should be lower."""
        ekf = NavigationEKF(q_pos_deg=1e-6)
        for _ in range(5):
            ekf.predict()
        s_before = ekf.position_uncertainty_1sigma()

        ekf.update_gnss(
            ins_lat=30.0, ins_lon=78.0, ins_alt=5000.0,
            gnss_lat=30.0, gnss_lon=78.0, gnss_alt=5000.0,
        )
        s_after = ekf.position_uncertainty_1sigma()
        # Lat uncertainty should decrease
        self.assertLess(s_after[0], s_before[0])


class TestEKFTANUpdate(unittest.TestCase):

    def test_tan_update_generates_correction(self):
        """TAN update with valid match should generate non-zero correction."""
        ekf = NavigationEKF(q_pos_deg=1e-6)
        ekf.predict()
        ekf.update_tan(
            ins_lat=30.0, ins_lon=78.0,
            tan_lat=30.002, tan_lon=78.002,
            match_score=0.8,
        )
        corr = ekf.get_correction()
        self.assertNotAlmostEqual(corr[0], 0.0, places=8)

    def test_low_match_score_has_larger_noise(self):
        """TAN update with low match score should produce smaller correction (larger R)."""
        ekf_low = NavigationEKF(q_pos_deg=1e-6)
        ekf_high = NavigationEKF(q_pos_deg=1e-6)
        ekf_low.predict()
        ekf_high.predict()

        ekf_low.update_tan(ins_lat=30.0, ins_lon=78.0,
                           tan_lat=30.01, tan_lon=78.01, match_score=0.01)
        ekf_high.update_tan(ins_lat=30.0, ins_lon=78.0,
                            tan_lat=30.01, tan_lon=78.01, match_score=0.99)

        corr_low  = ekf_low.get_correction()[0]
        corr_high = ekf_high.get_correction()[0]
        # High match score should produce larger correction (less noise, more trust)
        self.assertGreater(abs(corr_high), abs(corr_low))


class TestEKFMeasurementRejection(unittest.TestCase):

    def test_no_update_no_correction(self):
        """EKF that only predicts should have zero correction throughout."""
        ekf = NavigationEKF()
        for _ in range(10):
            ekf.predict()
        corr = ekf.get_correction()
        for v in corr:
            self.assertAlmostEqual(v, 0.0)

    def test_covariance_diagonal_positive(self):
        """All diagonal covariance entries must remain positive."""
        ekf = NavigationEKF()
        for _ in range(20):
            ekf.predict()
            ekf.update_gnss(
                ins_lat=30.0, ins_lon=78.0, ins_alt=5000.0,
                gnss_lat=30.001, gnss_lon=78.001, gnss_alt=5005.0,
            )
        cov = ekf.get_covariance_diagonal()
        for v in cov:
            self.assertGreater(v, 0.0)

    def test_ins_only_uncertainty_grows(self):
        """With no updates, position uncertainty grows with predictions."""
        ekf = NavigationEKF(q_pos_deg=1e-5)
        s0 = ekf.position_uncertainty_1sigma()[0]
        for _ in range(50):
            ekf.predict()
        s1 = ekf.position_uncertainty_1sigma()[0]
        self.assertGreater(s1, s0)


if __name__ == "__main__":
    unittest.main()
