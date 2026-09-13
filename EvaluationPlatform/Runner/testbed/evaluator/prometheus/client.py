import urllib.parse
import urllib.request
from datetime import datetime, timedelta


class PrometheusClient:
    def __init__(self, base_url: str | None) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None

    @property
    def enabled(self) -> bool:
        return self.base_url is not None

    def query(self, expression: str, timeout: int = 15) -> tuple[str, str]:
        url = f"{self.base_url}/api/v1/query?" + urllib.parse.urlencode(
            {"query": expression}
        )
        return url, self._get(url, timeout)

    def query_range(
        self,
        expression: str,
        start: datetime,
        end: datetime,
        step_seconds: int,
        timeout: int = 30,
    ) -> tuple[str, str]:
        if end <= start:
            end = start + timedelta(seconds=step_seconds)
        url = f"{self.base_url}/api/v1/query_range?" + urllib.parse.urlencode(
            {
                "query": expression,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "step": f"{step_seconds}s",
            }
        )
        return url, self._get(url, timeout)

    @staticmethod
    def _get(url: str, timeout: int) -> str:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8")
