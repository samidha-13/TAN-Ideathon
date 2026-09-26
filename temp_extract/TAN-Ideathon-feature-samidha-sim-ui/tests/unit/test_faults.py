import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from simulator.faults import FaultManager, GNSSStatus, SensorStatus

class TestFaults(unittest.TestCase):
    def test_fault_injection(self):
        fm = FaultManager()
        self.assertEqual(fm.gnss_status, GNSSStatus.AVAILABLE)
        
        fm.apply_scenario("GNSS denied")
        self.assertEqual(fm.gnss_status, GNSSStatus.DENIED)
        
        fm.apply_scenario("radar fault")
        self.assertEqual(fm.radar_status, SensorStatus.INVALID)
        
        fm.apply_scenario("magnetometer fault")
        self.assertEqual(fm.magnetometer_status, SensorStatus.INVALID)
        
        fm.apply_scenario("combined sensor failure")
        self.assertEqual(fm.gnss_status, GNSSStatus.DENIED)
        self.assertEqual(fm.radar_status, SensorStatus.INVALID)
        
        fm.apply_scenario("recovery")
        self.assertEqual(fm.gnss_status, GNSSStatus.AVAILABLE)
        self.assertEqual(fm.radar_status, SensorStatus.VALID)

if __name__ == '__main__':
    unittest.main()
