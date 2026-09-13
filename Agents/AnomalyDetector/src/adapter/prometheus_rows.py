from typing import Any


MetricRow = tuple[dict[str, str], float, str]


class PrometheusRowReader:
    """Extracts Prometheus result rows.

    Prerequisites:
    - Collector responses use the local HttpResult.ok shape.
    - Prometheus payloads contain either `value` or `values`.
    """

    def read(self, payload: dict[str, Any]) -> list[MetricRow]:
        response = payload.get("response")
        data = response.get("data") if isinstance(response, dict) else None
        result = data.get("result") if isinstance(data, dict) else None
        if not isinstance(result, list):
            raise ValueError("malformed Prometheus metric payload")
        rows = []
        for series in result:
            metric = series["metric"]
            if "value" in series:
                timestamp, value = series["value"]
                rows.append((metric, float(timestamp), value))
            else:
                rows.extend(
                    (metric, float(timestamp), value)
                    for timestamp, value in series["values"]
                )
        return rows
