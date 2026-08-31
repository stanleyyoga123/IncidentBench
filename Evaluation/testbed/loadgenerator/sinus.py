import math
import os
import random

from locust import LoadTestShape

class SinusLoadShape(LoadTestShape):
    """Move traffic smoothly between minimum and maximum user counts."""

    min_users = int(os.getenv("SINUS_MIN_USERS", "20"))
    max_users = int(os.getenv("SINUS_MAX_USERS", "150"))
    period_seconds = float(os.getenv("SINUS_PERIOD_SECONDS", "300"))
    run_time_seconds = float(os.getenv("RUN_TIME_SECONDS", "0"))
    spawn_rate = float(os.getenv("SINUS_SPAWN_RATE", "25"))
    bias_users = int(os.getenv("SINUS_BIAS_USERS", "0"))
    seed = int(os.getenv("SINUS_SEED", "1"))

    def __init__(self):
        super().__init__()
        self.rng = random.Random(self.seed)

    def tick(self):
        elapsed = self.get_run_time()
        if self.run_time_seconds > 0 and elapsed > self.run_time_seconds:
            return None

        amplitude = max(0, self.max_users - self.min_users) / 2
        midpoint = self.min_users + amplitude
        period = max(1.0, self.period_seconds)
        users = midpoint + amplitude * math.sin((2 * math.pi * elapsed) / period)
        bias = self.rng.randint(0, max(0, self.bias_users))

        return max(1, int(round(users)) + bias), self.spawn_rate
