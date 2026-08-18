from pathlib import Path

from ..command.command_runner import CommandRunner
from .metrics_collector import MetricsCollector
from .prometheus.client import PrometheusClient
from .prometheus.query_catalog import QueryCatalog
from .snapshot_collector import SnapshotCollector


class Evaluator:
    """Small facade composing independent snapshot and metric collectors."""

    def __init__(self, output_dir: Path, namespace: str = "online-boutique", prometheus_url: str | None = None) -> None:
        prometheus = PrometheusClient(prometheus_url)
        queries = QueryCatalog(namespace)
        runner = CommandRunner()
        self.snapshots = SnapshotCollector(output_dir, namespace, runner, prometheus, queries)
        self.metrics = MetricsCollector(output_dir, namespace, prometheus, queries)

    def collect_snapshot(self, label: str) -> dict:
        return self.snapshots.collect(label)

    def collect_metrics(self, start, end, rate_window: str = "1m", step_seconds: int = 15) -> dict:
        return self.metrics.collect(start, end, rate_window, step_seconds)
