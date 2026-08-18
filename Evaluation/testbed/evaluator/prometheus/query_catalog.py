from testbed.evaluator.collector import DEFAULT_QUERY_PARAMS, PROMETHEUS_QUERIES


class QueryCatalog:
    """Render the existing stable PromQL catalog for one namespace."""

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace

    def metric_queries(self, rate_window: str = "1m") -> dict[str, str]:
        params = DEFAULT_QUERY_PARAMS | {
            "namespace": self.namespace,
            "rate_window": rate_window,
        }
        return {
            name: template.format(**params)
            for name, template in PROMETHEUS_QUERIES.items()
        }

    def snapshot_queries(self) -> dict[str, str]:
        namespace = self.namespace
        return {
            "up": "up",
            "container_cpu_usage_rate": (
                f"sum(rate(container_cpu_usage_seconds_total{{namespace='{namespace}'}}[5m])) by (pod)"
            ),
            "container_memory_working_set": (
                f"sum(container_memory_working_set_bytes{{namespace='{namespace}'}}) by (pod)"
            ),
            "pod_restart_count": (
                f"sum(kube_pod_container_status_restarts_total{{namespace='{namespace}'}}) by (pod)"
            ),
        }
