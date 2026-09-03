from enum import Enum

class GNSSStatus(Enum):
    AVAILABLE = 1
    DEGRADED = 2
    DENIED = 3

class SensorStatus(Enum):
    VALID = 1
    INVALID = 2

class FaultManager:
    def __init__(self):
        self.gnss_status = GNSSStatus.AVAILABLE
        self.radar_status = SensorStatus.VALID
        self.magnetometer_status = SensorStatus.VALID

    def apply_scenario(self, scenario: str):
        if scenario == "baseline":
            self.gnss_status = GNSSStatus.AVAILABLE
            self.radar_status = SensorStatus.VALID
            self.magnetometer_status = SensorStatus.VALID
        elif scenario == "GNSS denied":
            self.gnss_status = GNSSStatus.DENIED
        elif scenario == "GNSS degraded":
            self.gnss_status = GNSSStatus.DEGRADED
        elif scenario == "radar fault":
            self.radar_status = SensorStatus.INVALID
        elif scenario == "magnetometer fault":
            self.magnetometer_status = SensorStatus.INVALID
        elif scenario == "combined sensor failure":
            self.gnss_status = GNSSStatus.DENIED
            self.radar_status = SensorStatus.INVALID
            self.magnetometer_status = SensorStatus.INVALID
        elif scenario == "recovery":
            self.apply_scenario("baseline")
        else:
            raise ValueError(f"Unknown fault scenario: {scenario}")
