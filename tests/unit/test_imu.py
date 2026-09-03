import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from simulator.imu_model import IMUModel
from synchronization.mission_state import MissionState

class TestIMU(unittest.TestCase):
    def test_imu_deterministic(self):
        # 10. IMU output is deterministic for same seed
        config = {'seed': 123}
        imu1 = IMUModel(config)
        imu2 = IMUModel(config)
        
        state = MissionState(0, 0.0, 30.0, 78.0, 1000.0, 200.0, 0.0, 0.0, 0.0)
        meas1 = imu1.generate_measurement(state)
        meas2 = imu2.generate_measurement(state)
        
        self.assertEqual(meas1, meas2)
        
    def test_imu_responds_to_state_changes(self):
        # 11. IMU values respond to trajectory/state changes
        config = {'seed': 123, 'accel_noise': 0, 'gyro_noise': 0}
        imu = IMUModel(config)
        
        state1 = MissionState(0, 0.0, 30.0, 78.0, 1000.0, 200.0, 0.0, 0.0, 0.0)
        state2 = MissionState(1, 0.1, 30.0, 78.0, 1000.0, 210.0, 0.1, 0.0, 0.0) # Accel and roll change
        
        imu.generate_measurement(state1)
        meas = imu.generate_measurement(state2)
        
        self.assertAlmostEqual(meas['ax'], (210 - 200) / 0.1)
        self.assertAlmostEqual(meas['roll_rate'], (0.1 - 0.0) / 0.1)

if __name__ == '__main__':
    unittest.main()
