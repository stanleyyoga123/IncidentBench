from __future__ import annotations


DEPLOYMENT_METRICS = {
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

NODE_METRICS = {
    "node_cpu_utilization_percent",
    "node_disk_io_bytes_per_second",
    "node_memory_utilization_percent",
    "node_network_io_bytes_per_second",
}

ALL_METRICS = DEPLOYMENT_METRICS | NODE_METRICS
RECORD_PREFIX = "anomaly_detector:"


class QueryBuilder:
    """Build inexpensive selectors over precomputed Prometheus recording rules."""

    @staticmethod
    def record_name(name: str) -> str:
        if name not in ALL_METRICS:
            raise KeyError(name)
        return f"{RECORD_PREFIX}{name}"

    @classmethod
    def build(
        cls,
        name: str,
        *,
        namespace_regex: str,
        deployment_regex: str = ".+",
        excluded_node_regex: str | None = None,
    ) -> str:
        record_name = cls.record_name(name)
        namespace_regex = cls._promql_string(namespace_regex)
        deployment_regex = cls._promql_string(deployment_regex)
        if name in DEPLOYMENT_METRICS:
            return (
                f'{record_name}{{namespace=~"{namespace_regex}",'
                f'deployment=~"{deployment_regex}"}}'
            )

        if excluded_node_regex:
            excluded_node_regex = cls._promql_string(excluded_node_regex)
            return f'{record_name}{{node!~"{excluded_node_regex}"}}'
        return record_name

    @staticmethod
    def names() -> list[str]:
        return sorted(ALL_METRICS)

    @classmethod
    def required_record_names(cls) -> set[str]:
        return {cls.record_name(name) for name in cls.names()}

    @staticmethod
    def _promql_string(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')


def format_query(name: str, **params: str) -> str:
    return QueryBuilder.build(name, **params)


def query_names() -> list[str]:
    return QueryBuilder.names()
