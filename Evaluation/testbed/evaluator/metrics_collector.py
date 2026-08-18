import json
from datetime import datetime, timezone
from pathlib import Path

from .prometheus.client import PrometheusClient
from .prometheus.query_catalog import QueryCatalog


class MetricsCollector:
    def __init__(self, output_dir: Path, namespace: str, prometheus: PrometheusClient, queries: QueryCatalog) -> None:
        self.output_dir = output_dir
        self.namespace = namespace
        self.prometheus = prometheus
        self.queries = queries

    def collect(self, start: datetime, end: datetime, rate_window: str = "1m", step_seconds: int = 15) -> dict:
        destination = self.output_dir / "metrics"
        destination.mkdir(parents=True, exist_ok=True)
        results = {"enabled": self.prometheus.enabled, "queries": []}
        if not self.prometheus.enabled:
            results["reason"] = "no prometheus url supplied"
        else:
            for name, expression in self.queries.metric_queries(rate_window).items():
                entry = {"name": name, "query": expression, "ok": False, "output_file": f"{name}.json"}
                try:
                    entry["url"], body = self.prometheus.query_range(expression, start, end, step_seconds)
                    entry["ok"] = True
                except Exception as exc:
                    body = json.dumps({"error": str(exc)}, indent=2)
                    entry["error"] = str(exc)
                (destination / entry["output_file"]).write_text(body)
                results["queries"].append(entry)
        metadata = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "namespace": self.namespace,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "rate_window": rate_window,
            "step_seconds": step_seconds,
            "prometheus": results,
        }
        (destination / "metrics.json").write_text(json.dumps(metadata, indent=2))
        return metadata
