from typing import Any

from tools.utility import apply_output_filter, http_get_json


class LokiTool:
    def __init__(self, base_url: str, timeout_seconds: int = 10) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def query(
        self,
        logql: str,
        query_type: str = "range",
        start: str | None = None,
        end: str | None = None,
        since: str | None = None,
        limit: int = 100,
        direction: str = "BACKWARD",
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = (
            "/loki/api/v1/query_range"
            if query_type == "range"
            else "/loki/api/v1/query"
        )
        params: dict[str, Any] = {
            "query": logql,
            "limit": limit,
            "direction": direction,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if since:
            params["since"] = since
        result = http_get_json(self.base_url, path, params, self.timeout_seconds)
        return apply_output_filter(result, filter)
