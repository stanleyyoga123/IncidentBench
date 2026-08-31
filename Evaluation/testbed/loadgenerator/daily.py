import os

from locust import LoadTestShape

class DailyTrafficShape(LoadTestShape):
    """Replay a 24-hour traffic curve. Edit `stages` here; 100% is DAILY_BASE_USERS."""

    base_users = float(
        os.getenv("DAILY_BASE_USERS", os.getenv("DAILY_BASE_USER", "600"))
    )
    run_time_seconds = float(os.getenv("RUN_TIME_SECONDS", "0"))
    stages = [
        # duration is cumulative seconds from locust start (treated as 00:00)

        # 00:00-06:00 overnight
        {"duration": 6 * 3600, "percentage_users": 20, "spawn_rate": 2},

        # 06:00-08:00 users coming online
        {"duration": 8 * 3600, "percentage_users": 40, "spawn_rate": 3},

        # 08:00-10:00 morning ramp
        {"duration": 10 * 3600, "percentage_users": 80, "spawn_rate": 5},

        # 10:00-10:15 short burst
        {"duration": 10.25 * 3600, "percentage_users": 200, "spawn_rate": 15},

        # 10:15-13:00 normal
        {"duration": 13 * 3600, "percentage_users": 75, "spawn_rate": 10},

        # 13:00-13:15 lunch/peak burst
        {"duration": 13.25 * 3600, "percentage_users": 250, "spawn_rate": 20},

        # 13:15-17:00 afternoon
        {"duration": 17 * 3600, "percentage_users": 90, "spawn_rate": 8},

        # 17:00-17:15 evening burst
        {"duration": 17.25 * 3600, "percentage_users": 150, "spawn_rate": 20},

        # 17:15-21:00 evening decline
        {"duration": 21 * 3600, "percentage_users": 60, "spawn_rate": 6},

        # 21:00-24:00 late night
        {"duration": 24 * 3600, "percentage_users": 25, "spawn_rate": 3},
    ]

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
