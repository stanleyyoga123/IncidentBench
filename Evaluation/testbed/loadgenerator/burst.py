import os
import random

from locust import LoadTestShape

class BurstLoadShape(LoadTestShape):
    """Alternate between a low baseline and short high-traffic bursts."""

    baseline_users = int(os.getenv("BURST_BASELINE_USERS", "300"))
    peak_users = int(os.getenv("BURST_PEAK_USERS", "1200"))
    baseline_seconds = float(os.getenv("BURST_BASELINE_SECONDS", "360"))
    peak_seconds = float(os.getenv("BURST_PEAK_SECONDS", "240"))
    run_time_seconds = float(os.getenv("RUN_TIME_SECONDS", "0"))
    spawn_rate = float(os.getenv("BURST_SPAWN_RATE", "200"))
    bias_users = int(os.getenv("BURST_BIAS_USERS", "20"))
    seed = int(os.getenv("BURST_SEED", "1"))

    def __init__(self):
        super().__init__()
        self.rng = random.Random(self.seed)

    def tick(self):
        elapsed = self.get_run_time()
        if self.run_time_seconds > 0 and elapsed > self.run_time_seconds:
            return None

        cycle_seconds = max(1.0, self.baseline_seconds + self.peak_seconds)
        position = elapsed % cycle_seconds
        users = (
            self.peak_users
            if position >= self.baseline_seconds
            else self.baseline_users
        )
        bias = self.rng.randint(0, max(0, self.bias_users))

        return max(1, users + bias), self.spawn_rate
