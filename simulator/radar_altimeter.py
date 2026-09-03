import random
from typing import Dict, Any
from typing_extensions import Protocol
from synchronization.mission_state import MissionState
from simulator.faults import FaultManager, SensorStatus

class TerrainElevationProvider(Protocol):
    def get_elevation(self, lat: float, lon: float) -> float:
        pass

class MockTerrainProvider:
    def get_elevation(self, lat: float, lon: float) -> float:
        return 100.0 # mock constant terrain

class RadarAltimeter:
    def __init__(self, config: Dict[str, Any], terrain_provider: TerrainElevationProvider):
        self.noise = config.get('radar_noise', 2.0)
        self.terrain_provider = terrain_provider
        self.rng = random.Random(config.get('seed', 42))

    def generate_measurement(self, state: MissionState, fault_manager: FaultManager) -> Dict[str, Any]:
        status = fault_manager.radar_status
        
        if status == SensorStatus.INVALID:
            return {
                'timestamp': state.timestamp,
                'status': 'INVALID',
                'latitude': state.latitude,
                'longitude': state.longitude,
                'altitude_above_ground_m': float('nan')
            }
            
        terrain_elev = self.terrain_provider.get_elevation(state.latitude, state.longitude)
        true_agl = state.altitude - terrain_elev
        measured_agl = true_agl + self.rng.gauss(0, self.noise)
        
        return {
            'timestamp': state.timestamp,
            'status': status.name,
            'latitude': state.latitude,
            'longitude': state.longitude,
            'altitude_above_ground_m': measured_agl
        }
