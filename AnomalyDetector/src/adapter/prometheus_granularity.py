MetricDict = dict[str, str | int | float]


class PrometheusGranularityTransformer:
    _DEPLOYMENT_METRICS = {
        "app_instance_count",
        "deployment_cpu_usage",
        "deployment_cpu_request_utilization_percent",
        "deployment_memory_request_utilization_percent",
        "deployment_disk_io_bytes_per_second",
        "deployment_network_io_bytes_per_second",
        "http_5xx_rate",
        "response_time_p95_seconds",
        "traffic_rps",
    }
    _NODE_METRICS = {
        "node_cpu_utilization_percent",
        "node_disk_io_bytes_per_second",
        "node_memory_utilization_percent",
        "node_network_io_bytes_per_second",
    }

    def transform(
        self,
        adapted: dict[str, list[MetricDict]],
    ) -> dict[str, dict[str, dict[str, list[MetricDict]]]]:
        return {
            "deployments": self._group(
                adapted=adapted,
                metric_names=self._DEPLOYMENT_METRICS,
                keys=("deployment", "workload"),
            ),
            "nodes": self._group(
                adapted=adapted,
                metric_names=self._NODE_METRICS,
                keys=("node",),
            ),
        }

    def _group(
        self,
        adapted: dict[str, list[MetricDict]],
        metric_names: set[str],
        keys: tuple[str, ...],
    ) -> dict[str, dict[str, list[MetricDict]]]:
        grouped: dict[str, dict[str, list[MetricDict]]] = {}
        for metric_name, rows in adapted.items():
            if metric_name not in metric_names:
                continue
            for row in rows:
                name = self._name(row, keys)
                if metric_name in self._DEPLOYMENT_METRICS:
                    namespace = str(row.get("namespace", "")).strip()
                    if not namespace:
                        raise KeyError("namespace")
                    name = f"{namespace}/{name}"
                grouped.setdefault(name, {}).setdefault(metric_name, []).append(row)
        return grouped

    @staticmethod
    def _name(row: MetricDict, keys: tuple[str, ...]) -> str:
        for key in keys:
            if key in row:
                return str(row[key])
        raise KeyError(keys[0])
