from testbed.loadgenerator.settings import defaults
_defaults = defaults('daily')

from locust import LoadTestShape

class DailyTrafficShape(LoadTestShape):
    """Replay a 24-hour traffic curve. Stages are cumulative seconds; 100% is base_users."""

    base_users = _defaults['base_users']
    run_time_seconds = 0
    stages = _defaults["stages"]

    def tick(self):
        run_time = self.get_run_time()
        if self.run_time_seconds > 0 and run_time > self.run_time_seconds:
            return None

        day = self.stages[-1]["duration"]
        position = run_time % day if day > 0 else run_time
        for stage in self.stages:
            if position < stage["duration"]:
                users = int(round(self.base_users * stage["percentage_users"] / 100.0))
                return max(1, users), stage["spawn_rate"]
        return None
