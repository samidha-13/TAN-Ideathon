import random
from typing import Dict, Any
from synchronization.mission_state import MissionState
from simulator.faults import FaultManager, GNSSStatus

class GNSSModel:
    def __init__(self, config: Dict[str, Any]):
        self.noise_pos = config.get('gnss_noise_pos', 2.0) # approx meters
        self.noise_alt = config.get('gnss_noise_alt', 3.0) # meters
        self.noise_vel = config.get('gnss_noise_vel', 0.1) # m/s
        self.rng = random.Random(config.get('seed', 42))

    def generate_measurement(self, state: MissionState, fault_manager: FaultManager) -> Dict[str, Any]:
        status = fault_manager.gnss_status
        
        if status == GNSSStatus.DENIED:
            return {
                'timestamp': state.timestamp,
                'status': 'DENIED',
                'latitude': float('nan'),
                'longitude': float('nan'),
                'altitude': float('nan'),
                'velocity': float('nan')
            }
            
        # Add noise
        noise_mult = 5.0 if status == GNSSStatus.DEGRADED else 1.0
        
        # 1 degree lat is ~ 111.32 km
        lat_noise_deg = (self.rng.gauss(0, self.noise_pos * noise_mult)) / 111320.0
        import math
        lon_noise_deg = (self.rng.gauss(0, self.noise_pos * noise_mult)) / (111320.0 * math.cos(math.radians(state.latitude)))
        
        lat = state.latitude + lat_noise_deg
        lon = state.longitude + lon_noise_deg
        alt = state.altitude + self.rng.gauss(0, self.noise_alt * noise_mult)
        vel = state.velocity + self.rng.gauss(0, self.noise_vel * noise_mult)
        
        return {
            'timestamp': state.timestamp,
            'status': status.name,
            'latitude': lat,
            'longitude': lon,
            'altitude': alt,
            'velocity': vel
        }
