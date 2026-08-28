"""Read Prometheus query-range exports for offline visualization."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MetricSeries:
    label: str
    labels: dict[str, str]
    elapsed_minutes: tuple[float, ...]
    values: tuple[float, ...]


@dataclass(frozen=True)
class MetricDataset:
    name: str
    title: str
    unit: str
    series: tuple[MetricSeries, ...]


METRIC_PRESENTATION = {
    "app_instance_count": ("Application instance count", "replicas"),
    "deployment_cpu_request_utilization_percent": ("Deployment CPU request utilization", "%"),
    "deployment_cpu_usage": ("Deployment CPU usage", "CPU cores"),
    "deployment_disk_io_bytes_per_second": ("Deployment disk I/O", "bytes/s"),
    "deployment_memory_request_utilization_percent": ("Deployment memory request utilization", "%"),
    "deployment_network_io_bytes_per_second": ("Deployment network I/O", "bytes/s"),
    "http_5xx_rate": ("HTTP 5xx rate", "requests/s"),
    "node_cpu_utilization_percent": ("Node CPU utilization", "%"),
    "node_disk_io_bytes_per_second": ("Node disk I/O", "bytes/s"),
    "node_memory_utilization_percent": ("Node memory utilization", "%"),
    "node_network_io_bytes_per_second": ("Node network I/O", "bytes/s"),
    "response_time_p95_seconds": ("Response-time P95", "seconds"),
    "traffic_rps": ("Traffic", "requests/s"),
}


def _series_label(labels: dict[str, str], index: int) -> str:
    for key in ("deployment", "destination_workload", "node", "pod", "app", "service", "instance"):
        value = labels.get(key)
        if value:
            return value
    return f"series-{index + 1}"


def _load_metric(path: Path, origin: datetime) -> MetricDataset | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    results = payload.get("data", {}).get("result", []) if isinstance(payload, dict) else []
    if not isinstance(results, list):
        raise ValueError(f"Prometheus result is not a list: {path}")

    parsed: list[MetricSeries] = []
    used_labels: dict[str, int] = {}
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            continue
        raw_labels = result.get("metric", {})
        labels = {str(key): str(value) for key, value in raw_labels.items()} if isinstance(raw_labels, dict) else {}
        base_label = _series_label(labels, index)
        used_labels[base_label] = used_labels.get(base_label, 0) + 1
        suffix = used_labels[base_label]
        label = base_label if suffix == 1 else f"{base_label} ({suffix})"
        elapsed: list[float] = []
        values: list[float] = []
        samples = result.get("values", [])
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, (list, tuple)) or len(sample) < 2:
                continue
            try:
                timestamp = float(sample[0])
                value = float(sample[1])
            except (TypeError, ValueError):
                continue
            if not math.isfinite(timestamp) or not math.isfinite(value):
                continue
            elapsed.append((timestamp - origin.timestamp()) / 60.0)
            values.append(value)
        if elapsed:
            ordered = sorted(zip(elapsed, values), key=lambda item: item[0])
            parsed.append(
                MetricSeries(label, labels, tuple(item[0] for item in ordered), tuple(item[1] for item in ordered))
            )

    if not parsed:
        return None
    title, unit = METRIC_PRESENTATION.get(path.stem, (path.stem.replace("_", " ").title(), "value"))
    return MetricDataset(path.stem, title, unit, tuple(parsed))


def load_run_metrics(run_dir: Path, origin: datetime) -> tuple[MetricDataset, ...]:
    """Load every non-summary metric file for a run in filename order."""

    metrics_dir = Path(run_dir) / "metrics"
    if not metrics_dir.is_dir():
        return ()
    datasets: list[MetricDataset] = []
    for path in sorted(metrics_dir.glob("*.json")):
        if path.name == "metrics.json":
            continue
        dataset = _load_metric(path, origin)
        if dataset is not None:
            datasets.append(dataset)
    return tuple(datasets)
