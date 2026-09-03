import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from simulator.radar_altimeter import RadarAltimeter, MockTerrainProvider
from simulator.faults import FaultManager
from synchronization.mission_state import MissionState

class TestRadar(unittest.TestCase):
    def setUp(self):
        self.radar = RadarAltimeter({'seed': 123, 'radar_noise': 0.0}, MockTerrainProvider())
        self.fm = FaultManager()
        self.state = MissionState(0, 0.0, 30.0, 78.0, 1000.0, 200.0, 0.0, 0.0, 0.0)

    def test_radar_interface(self):
        # 15. Radar uses terrain provider
        meas = self.radar.generate_measurement(self.state, self.fm)
        self.assertEqual(meas['altitude_above_ground_m'], 1000.0 - 100.0)
        
    def test_radar_fault(self):
        # 17. Radar fault is correctly injected
        self.fm.apply_scenario("radar fault")
        meas = self.radar.generate_measurement(self.state, self.fm)
        self.assertEqual(meas['status'], 'INVALID')
        import math
        self.assertTrue(math.isnan(meas['altitude_above_ground_m']))

if __name__ == '__main__':
    unittest.main()
