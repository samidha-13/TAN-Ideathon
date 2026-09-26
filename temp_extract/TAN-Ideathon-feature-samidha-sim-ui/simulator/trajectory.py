import math
import random
from typing import List, Dict, Any, Tuple
from synchronization.mission_state import MissionState
from synchronization.mission_clock import MissionClock

def validate_position(lat: float, lon: float, bounds: Dict[str, float]) -> bool:
    """Check if lat/lon are within the specified bounds."""
    if lat < bounds['lat_min'] or lat > bounds['lat_max']:
        return False
    if lon < bounds['lon_min'] or lon > bounds['lon_max']:
        return False
    return True

def calculate_distance_and_heading(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float]:
    """Calculate distance (meters) and initial bearing (radians) between two points."""
    R = 6371000.0 # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c

    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    heading = math.atan2(y, x)
    
    return distance, heading

class TrajectoryGenerator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.bounds = config['bounds']
        self.waypoints = config['waypoints']
        self.altitude = config.get('altitude', 1000.0)
        self.velocity = config.get('velocity', 200.0)
        
        self.clock = MissionClock(sample_rate=config.get('sample_rate', 10.0))
        self.dt = self.clock.dt
        
        random.seed(config.get('seed', 42))

    def generate(self) -> List[MissionState]:
        states = []
        
        if len(self.waypoints) < 2:
            raise ValueError("Need at least 2 waypoints")
            
        current_lat = self.waypoints[0]['lat']
        current_lon = self.waypoints[0]['lon']
        
        # Verify initial point
        if not validate_position(current_lat, current_lon, self.bounds):
            raise ValueError(f"Starting position {current_lat}, {current_lon} out of bounds")

        R = 6371000.0
        
        current_wp_idx = 0
        heading = 0.0
        
        while current_wp_idx < len(self.waypoints) - 1:
            target_wp = self.waypoints[current_wp_idx + 1]
            
            while True:
                dist, heading = calculate_distance_and_heading(current_lat, current_lon, target_wp['lat'], target_wp['lon'])
                
                # Check if we reached the waypoint
                if dist <= self.velocity * self.dt:
                    current_lat = target_wp['lat']
                    current_lon = target_wp['lon']
                    break
                    
                # Move towards target
                lat_change_rate = self.velocity * math.cos(heading) / R
                lon_change_rate = self.velocity * math.sin(heading) / (R * math.cos(math.radians(current_lat)))
                
                current_lat += math.degrees(lat_change_rate * self.dt)
                current_lon += math.degrees(lon_change_rate * self.dt)
                
                if not validate_position(current_lat, current_lon, self.bounds):
                    raise ValueError(f"Trajectory left bounding box: lat={current_lat}, lon={current_lon}")
                
                # Generate state
                state = MissionState(
                    mission_index=self.clock.get_index(),
                    timestamp=self.clock.get_time(),
                    latitude=current_lat,
                    longitude=current_lon,
                    altitude=self.altitude,
                    velocity=self.velocity,
                    roll=0.0,
                    pitch=0.0,
                    yaw=heading
                )
                states.append(state)
                self.clock.tick()
                
            current_wp_idx += 1
            
        # Ensure we add the last point
        state = MissionState(
            mission_index=self.clock.get_index(),
            timestamp=self.clock.get_time(),
            latitude=current_lat,
            longitude=current_lon,
            altitude=self.altitude,
            velocity=self.velocity,
            roll=0.0,
            pitch=0.0,
            yaw=heading # reuse last heading
        )
        states.append(state)
        
        return states
