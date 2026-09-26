class MissionClock:
    """
    Deterministic mission clock.
    """
    def __init__(self, sample_rate: float = 10.0):
        self.sample_rate = sample_rate
        self.dt = 1.0 / sample_rate
        self.current_index = 0
        self.current_time = 0.0

    def tick(self) -> float:
        """Advance the clock by one step and return the new timestamp."""
        self.current_time += self.dt
        self.current_index += 1
        return self.current_time

    def get_time(self) -> float:
        return self.current_time
        
    def get_index(self) -> int:
        return self.current_index
        
    def reset(self):
        self.current_index = 0
        self.current_time = 0.0
