import unittest
import sys
import os
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from simulator.magnetometer import Magnetometer, MockMagneticProvider
from simulator.faults import FaultManager
from synchronization.mission_state import MissionState

class TestMagnetometer(unittest.TestCase):
    def setUp(self):
        self.mag = Magnetometer({'seed': 123, 'mag_noise': 0.0, 'mag_bias': 50.0}, MockMagneticProvider())
        self.fm = FaultManager()
        self.state = MissionState(0, 0.0, 30.0, 78.0, 1000.0, 200.0, 0.0, 0.0, 0.0)

    def test_magnetometer_interface(self):
        # 16. Magnetometer uses magnetic ref provider
        meas = self.mag.generate_measurement(self.state, self.fm)
        self.assertAlmostEqual(meas['mag_x'], 30000.0 + 50.0)
        
    def test_magnetometer_fault(self):
        # 18. Magnetometer fault correctly injected
        self.fm.apply_scenario("magnetometer fault")
        meas = self.mag.generate_measurement(self.state, self.fm)
        self.assertEqual(meas['status'], 'INVALID')
        self.assertTrue(math.isnan(meas['mag_x']))

if __name__ == '__main__':
    unittest.main()
