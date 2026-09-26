import unittest
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from simulator.trajectory import TrajectoryGenerator, validate_position

class TestTrajectory(unittest.TestCase):
    def setUp(self):
        missions = ['mountain_mission', 'desert_mission', 'western_ghats_mission', 'flat_plain_mission']
        self.configs = []
        for m in missions:
            config_path = os.path.join(os.path.dirname(__file__), f'../../configs/missions/{m}.json')
            with open(config_path, 'r') as f:
                self.configs.append(json.load(f))
                
    def test_load_all_missions(self):
        self.assertEqual(len(self.configs), 4)
        
    def test_trajectory_bounds(self):
        for config in self.configs:
            gen = TrajectoryGenerator(config)
            states = gen.generate()
            self.assertTrue(len(states) > 0)
            
            for state in states:
                # 4, 5, 6: Check every generated state is inside bounds
                self.assertTrue(config['bounds']['lat_min'] <= state.latitude <= config['bounds']['lat_max'], f"Lat out of bounds in {config['mission_name']}")
                self.assertTrue(config['bounds']['lon_min'] <= state.longitude <= config['bounds']['lon_max'], f"Lon out of bounds in {config['mission_name']}")
                
    def test_trajectory_deterministic(self):
        # 7. Trajectory generation is deterministic
        gen1 = TrajectoryGenerator(self.configs[0])
        states1 = gen1.generate()
        
        gen2 = TrajectoryGenerator(self.configs[0])
        states2 = gen2.generate()
        
        self.assertEqual(len(states1), len(states2))
        for s1, s2 in zip(states1, states2):
            self.assertEqual(s1.latitude, s2.latitude)
            self.assertEqual(s1.longitude, s2.longitude)
            self.assertEqual(s1.timestamp, s2.timestamp)

if __name__ == '__main__':
    unittest.main()
