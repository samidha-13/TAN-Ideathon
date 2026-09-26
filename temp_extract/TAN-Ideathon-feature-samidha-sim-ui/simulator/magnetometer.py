import random
from typing import Dict, Any, Tuple
from typing_extensions import Protocol
from synchronization.mission_state import MissionState
from simulator.faults import FaultManager, SensorStatus

class MagneticReferenceProvider(Protocol):
    def get_magnetic_reference(self, lat: float, lon: float) -> Tuple[float, float, float]:
        pass

class MockMagneticProvider:
    def get_magnetic_reference(self, lat: float, lon: float) -> Tuple[float, float, float]:
        return (30000.0, 1000.0, 40000.0) # mock Bx, By, Bz in nT

class Magnetometer:
    def __init__(self, config: Dict[str, Any], mag_provider: MagneticReferenceProvider):
        self.noise = config.get('mag_noise', 10.0) # nT
        self.bias = config.get('mag_bias', 50.0) # nT
        self.mag_provider = mag_provider
        self.rng = random.Random(config.get('seed', 42))

    def generate_measurement(self, state: MissionState, fault_manager: FaultManager) -> Dict[str, Any]:
        status = fault_manager.magnetometer_status
        
        if status == SensorStatus.INVALID:
            return {
                'timestamp': state.timestamp,
                'status': 'INVALID',
                'latitude': state.latitude,
                'longitude': state.longitude,
                'mag_x': float('nan'),
                'mag_y': float('nan'),
                'mag_z': float('nan')
            }
            
        bx_true, by_true, bz_true = self.mag_provider.get_magnetic_reference(state.latitude, state.longitude)
        
        bx_meas = bx_true + self.bias + self.rng.gauss(0, self.noise)
        by_meas = by_true + self.bias + self.rng.gauss(0, self.noise)
        bz_meas = bz_true + self.bias + self.rng.gauss(0, self.noise)
        
        return {
            'timestamp': state.timestamp,
            'status': status.name,
            'latitude': state.latitude,
            'longitude': state.longitude,
            'mag_x': bx_meas,
            'mag_y': by_meas,
            'mag_z': bz_meas
        }
