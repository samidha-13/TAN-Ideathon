from dataclasses import dataclass

@dataclass
class MissionState:
    mission_index: int
    timestamp: float      # seconds
    latitude: float       # degrees
    longitude: float      # degrees
    altitude: float       # meters
    velocity: float       # meters/second
    roll: float           # radians
    pitch: float          # radians
    yaw: float            # radians
