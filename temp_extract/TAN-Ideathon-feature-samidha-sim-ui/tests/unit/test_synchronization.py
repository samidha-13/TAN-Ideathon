import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from synchronization.mission_clock import MissionClock
from synchronization.mission_state import MissionState

class TestSynchronization(unittest.TestCase):
    def test_mission_clock_deterministic(self):
        # 9. Mission clock is deterministic
        clock = MissionClock(10.0)
        self.assertEqual(clock.get_time(), 0.0)
        clock.tick()
        self.assertAlmostEqual(clock.get_time(), 0.1)
        clock.tick()
        self.assertAlmostEqual(clock.get_time(), 0.2)
        
    def test_mission_state_fields(self):
        # 8. MissionState fields are valid
        state = MissionState(0, 0.0, 30.0, 78.0, 1000.0, 200.0, 0.0, 0.0, 0.0)
        self.assertEqual(state.mission_index, 0)
        self.assertEqual(state.timestamp, 0.0)
        self.assertEqual(state.latitude, 30.0)

if __name__ == '__main__':
    unittest.main()
