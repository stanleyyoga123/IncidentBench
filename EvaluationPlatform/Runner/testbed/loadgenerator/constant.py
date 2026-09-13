from testbed.loadgenerator.settings import defaults
_defaults = defaults('constant')
import random

from locust import LoadTestShape

class ConstantLoadShape(LoadTestShape):
    """Drive total users with a stable base count plus a small upward bias."""

    users = _defaults['users']
    bias_users = _defaults['bias_users']
    run_time_seconds = 0
    spawn_rate = _defaults['spawn_rate']
    seed = _defaults['seed']

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
