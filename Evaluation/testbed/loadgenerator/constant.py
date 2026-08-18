import os
import random

from locust import LoadTestShape

from testbed.loadgenerator.common import WebsiteUser


class ConstantLoadShape(LoadTestShape):
    """Drive total users with a stable base count plus a small upward bias."""

    users = int(os.getenv("CONST_USERS", "50"))
    bias_users = int(os.getenv("CONST_BIAS_USERS", "3"))
    run_time_seconds = float(
        os.getenv("CONST_RUN_TIME_SECONDS", os.getenv("RUN_TIME_SECONDS", "0"))
    )
    spawn_rate = float(os.getenv("CONST_SPAWN_RATE", "10"))
    seed = int(os.getenv("CONST_SEED", "1"))

    def __init__(self):
        super().__init__()
        self.rng = random.Random(self.seed)

    def tick(self):
        elapsed = self.get_run_time()

        if self.run_time_seconds > 0 and elapsed > self.run_time_seconds:
            return None

        bias = self.rng.randint(0, max(0, self.bias_users))
        user_count = max(1, self.users + bias)

        return user_count, self.spawn_rate
