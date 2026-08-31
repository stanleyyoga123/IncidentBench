from dataclasses import dataclass
from typing import Any

from adapter.prometheus_rows import PrometheusRowReader

MetricDict = dict[str, str | int | float]


@dataclass(frozen=True)
class PrometheusMetricSpec:
    label: str
    output_key: str
    integer_value: bool = False


class PrometheusMetricAdapter:
    _SPECS = {
        "app_instance_count": PrometheusMetricSpec(
            label="deployment",
            output_key="deployment",
            integer_value=True,
        ),
        "deployment_cpu_usage": PrometheusMetricSpec(
            label="deployment",
            output_key="deployment",
        ),
        "deployment_cpu_request_utilization_percent": PrometheusMetricSpec(
            label="deployment",
            output_key="deployment",
        ),
        "deployment_memory_request_utilization_percent": PrometheusMetricSpec(
            label="deployment",
            output_key="deployment",
        ),
        "deployment_disk_io_bytes_per_second": PrometheusMetricSpec(
            label="deployment",
            output_key="deployment",
        ),
        "deployment_network_io_bytes_per_second": PrometheusMetricSpec(
            label="deployment",
            output_key="deployment",
        ),
        "http_5xx_rate": PrometheusMetricSpec(
            label="deployment",
            output_key="deployment",
        ),
        "response_time_p95_seconds": PrometheusMetricSpec(
            label="deployment",
            output_key="deployment",
        ),
        "traffic_rps": PrometheusMetricSpec(
            label="deployment",
            output_key="deployment",
        ),
        "node_cpu_utilization_percent": PrometheusMetricSpec(
            label="node",
            output_key="node",
        ),
        "node_disk_io_bytes_per_second": PrometheusMetricSpec(
            label="node",
            output_key="node",
        ),
        "node_memory_utilization_percent": PrometheusMetricSpec(
            label="node",
            output_key="node",
        ),
        "node_network_io_bytes_per_second": PrometheusMetricSpec(
            label="node",
            output_key="node",
        ),
    }

    def __init__(self):
        self._reader = PrometheusRowReader()

    def adapt(self, payload: dict[str, Any]) -> dict[str, list[MetricDict]]:
        return {
            metric_name: self._adapt_metric(item, self._SPECS[metric_name])
            for metric_name, item in payload.items()
        }

    def _adapt_metric(
        self,
        payload: dict[str, Any],
        spec: PrometheusMetricSpec,
    ) -> list[MetricDict]:
        rows = []
        for metric, timestamp, value in self._reader.read(payload):
            row: MetricDict = {
                "timestamp": timestamp,
                spec.output_key: metric[spec.label],
                "value": self._value(value, spec),
            }
            if spec.output_key == "deployment":
                row["namespace"] = metric["namespace"]
            rows.append(row)
        return rows

    @staticmethod
    def _value(value: str, spec: PrometheusMetricSpec) -> int | float:
        if spec.integer_value:
            return int(float(value))
        return float(value)
