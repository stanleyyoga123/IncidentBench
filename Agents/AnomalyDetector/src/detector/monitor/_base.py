from datetime import datetime, timedelta


class _BaseMonitor:
    def __init__(self, cooldown_seconds: float):
        self._cooldowns = {}
        self._cooldown_seconds = cooldown_seconds

    def _check_cooldown(self):
        now = datetime.now()
        keys = [key for key, ts in self._cooldowns.items() if ts <= now]
        for key in keys:
            del self._cooldowns[key]

    def _add_cooldown(self, key: str):
        self._cooldowns[key] = datetime.now() + timedelta(
            seconds=self._cooldown_seconds
        )

    def acknowledge(self, keys: set[str]) -> None:
        """Start cooldown only after the anomaly sink acknowledges delivery."""
        for key in keys:
            self._add_cooldown(key)
