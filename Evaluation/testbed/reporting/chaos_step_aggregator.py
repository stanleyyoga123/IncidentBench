from pathlib import Path

import numpy as np
import pandas as pd

from .chaos_window import ChaosWindowReader
from .locust_metric_reader import LocustMetricReader
from .metadata_reader import MetadataReader
from .prometheus_metric_reader import PrometheusMetricReader


class ChaosStepAggregator:
    def __init__(self) -> None:
        self.metadata = MetadataReader()
        self.windows = ChaosWindowReader()
        self.prometheus = PrometheusMetricReader()
        self.locust = LocustMetricReader()

    def aggregate(self, runs: list[Path]) -> pd.DataFrame:
        rows = []
        for run in runs:
            metadata = self.metadata.read(run)
            for window in self.windows.windows(metadata):
                rows.append(self._aggregate_window(run, metadata, window))
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).sort_values(
            ["scenario", "placement", "step_index", "mode", "run"]
        ).reset_index(drop=True)

    def _aggregate_window(self, run, metadata, window):
        metric = lambda name: self.prometheus.read(run, name, window.start, window.end)
        cpu, p95 = metric("deployment_cpu_usage"), metric("response_time_p95_seconds")
        rps, errors = metric("traffic_rps"), metric("http_5xx_rate")
        instances = metric("app_instance_count")
        locust = self.locust.read_window(run, window.start, window.end)
        return {
            "run": Path(run).name,
            "scenario": metadata.get("scenario", {}).get("name", Path(run).name),
            "placement": metadata.get("placement", {}).get(
                "reference", "unmanaged"
            ),
            "placement_fingerprint": metadata.get("placement", {}).get(
                "observed_placement_fingerprint", "unknown"
            )
            or "unknown",
            "placement_definition_fingerprint": metadata.get("placement", {}).get(
                "rendered_sha256", "unknown"
            )
            or "unknown",
            "mode": "agent" if metadata.get("agents_enabled") else "non-agent",
            "step_index": window.step_index,
            "step_name": window.step_name,
            "chaos": ",".join(window.chaos),
            "schedule_types": ",".join(window.schedule_types),
            "actions": ",".join(window.actions),
            "step_status": window.status,
            "duration_seconds": window.end - window.start,
            "avg_cpu_cores": self._time_total(cpu).mean(),
            "peak_cpu_cores": self._time_total(cpu).max(),
            "avg_response_ms": locust.get("avg_response_ms", np.nan),
            "avg_p95_ms": p95["value"].mean() * 1000 if not p95.empty else np.nan,
            "peak_p95_ms": p95["value"].max() * 1000 if not p95.empty else np.nan,
            "avg_rps": self._time_total(rps).mean(),
            "avg_5xx_rps": self._time_total(errors).mean(),
            "failure_pct": locust.get("failure_pct", np.nan),
            "avg_instances": self._time_total(instances).mean(),
        }

    @staticmethod
    def _time_total(frame):
        if frame.empty:
            return pd.Series(dtype=float)
        return frame.groupby("timestamp")["value"].sum()
