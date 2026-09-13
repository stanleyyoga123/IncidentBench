from testbed.loadgenerator.settings import defaults
_defaults = defaults('sinus')
import math
import random

from locust import LoadTestShape

class SinusLoadShape(LoadTestShape):
    """Move traffic smoothly between minimum and maximum user counts."""

    min_users = _defaults['min_users']
    max_users = _defaults['max_users']
    period_seconds = _defaults['period_seconds']
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

        amplitude = max(0, self.max_users - self.min_users) / 2
        midpoint = self.min_users + amplitude
        period = max(1.0, self.period_seconds)
        users = midpoint + amplitude * math.sin((2 * math.pi * elapsed) / period)
        bias = self.rng.randint(0, max(0, self.bias_users))

        return max(1, int(round(users)) + bias), self.spawn_rate
