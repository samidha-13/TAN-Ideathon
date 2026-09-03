import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from simulator.gnss_model import GNSSModel
from simulator.faults import FaultManager
from synchronization.mission_state import MissionState

class TestGNSS(unittest.TestCase):
    def setUp(self):
        self.gnss = GNSSModel({'seed': 123})
        self.fm = FaultManager()
        self.state = MissionState(0, 0.0, 30.0, 78.0, 1000.0, 200.0, 0.0, 0.0, 0.0)

    def test_gnss_normal(self):
        # 12. GNSS produces valid measurements during normal operation
        meas = self.gnss.generate_measurement(self.state, self.fm)
        self.assertEqual(meas['status'], 'AVAILABLE')
        self.assertFalse(import_math_isnan(meas['latitude']))
        
    def test_gnss_denial(self):
        # 13. GNSS denial makes GNSS unavailable
        self.fm.apply_scenario("GNSS denied")
        meas = self.gnss.generate_measurement(self.state, self.fm)
        self.assertEqual(meas['status'], 'DENIED')
        self.assertTrue(import_math_isnan(meas['latitude']))

    def test_gnss_degraded(self):
        # 14. GNSS degradation changes status/measurement quality
        self.fm.apply_scenario("GNSS degraded")
        meas = self.gnss.generate_measurement(self.state, self.fm)
        self.assertEqual(meas['status'], 'DEGRADED')

def import_math_isnan(v):
    import math
    return math.isnan(v)

if __name__ == '__main__':
    unittest.main()
