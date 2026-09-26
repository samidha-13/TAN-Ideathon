import random
from typing import Dict, Any, Optional
from synchronization.mission_state import MissionState

class IMUModel:
    def __init__(self, config: Dict[str, Any]):
        self.accel_bias = config.get('accel_bias', 0.0)
        self.accel_noise = config.get('accel_noise', 0.01)
        self.gyro_bias = config.get('gyro_bias', 0.0)
        self.gyro_noise = config.get('gyro_noise', 0.001)
        
        self.rng = random.Random(config.get('seed', 42))
        self.prev_state: Optional[MissionState] = None

    def generate_measurement(self, state: MissionState) -> Dict[str, float]:
        if self.prev_state is None:
            dt = 0.1
            prev_vel = state.velocity
            prev_roll = state.roll
            prev_pitch = state.pitch
            prev_yaw = state.yaw
        else:
            dt = state.timestamp - self.prev_state.timestamp
            if dt <= 0:
                dt = 0.1
            prev_vel = self.prev_state.velocity
            prev_roll = self.prev_state.roll
            prev_pitch = self.prev_state.pitch
            prev_yaw = self.prev_state.yaw

        # Simple derivative for acceleration (assuming forward motion mainly)
        accel_forward = (state.velocity - prev_vel) / dt
        
        # Simple derivative for rates
        # Handling wrap-around for yaw
        dyaw = state.yaw - prev_yaw
        import math
        if dyaw > math.pi:
            dyaw -= 2 * math.pi
        elif dyaw < -math.pi:
            dyaw += 2 * math.pi

        roll_rate = (state.roll - prev_roll) / dt
        pitch_rate = (state.pitch - prev_pitch) / dt
        yaw_rate = dyaw / dt

        # Add gravity to az (assuming Z is down, X is forward)
        g = 9.81
        ax = accel_forward + self.accel_bias + self.rng.gauss(0, self.accel_noise)
        ay = 0.0 + self.accel_bias + self.rng.gauss(0, self.accel_noise)
        az = -g + self.accel_bias + self.rng.gauss(0, self.accel_noise)

        rr = roll_rate + self.gyro_bias + self.rng.gauss(0, self.gyro_noise)
        pr = pitch_rate + self.gyro_bias + self.rng.gauss(0, self.gyro_noise)
        yr = yaw_rate + self.gyro_bias + self.rng.gauss(0, self.gyro_noise)

        self.prev_state = state

        return {
            'timestamp': state.timestamp,
            'ax': ax,
            'ay': ay,
            'az': az,
            'roll_rate': rr,
            'pitch_rate': pr,
            'yaw_rate': yr
        }
