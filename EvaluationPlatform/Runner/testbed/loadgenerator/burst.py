from testbed.loadgenerator.settings import defaults
_defaults = defaults('burst')
import random

from locust import LoadTestShape

class BurstLoadShape(LoadTestShape):
    """Alternate between a low baseline and short high-traffic bursts."""

    baseline_users = _defaults['baseline_users']
    peak_users = _defaults['peak_users']
    baseline_seconds = _defaults['baseline_seconds']
    peak_seconds = _defaults['peak_seconds']
    run_time_seconds = 0
    spawn_rate = _defaults['spawn_rate']
    bias_users = _defaults['bias_users']
    seed = _defaults['seed']

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
