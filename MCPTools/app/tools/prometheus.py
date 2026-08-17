from typing import Any

from tools.utility import apply_output_filter, http_get_json


class PrometheusTool:
    def __init__(self, base_url: str, timeout_seconds: int = 10) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def query(
        self,
        promql: str,
        query_type: str = "instant",
        time: str | None = None,
        start: str | None = None,
        end: str | None = None,
        step: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = "/api/v1/query"
        params: dict[str, Any] = {"query": promql}
        if query_type == "range":
            path = "/api/v1/query_range"
            params.update({"start": start, "end": end, "step": step})
        elif time:
            params["time"] = time
        result = http_get_json(self.base_url, path, params, self.timeout_seconds)
        return apply_output_filter(result, filter)
