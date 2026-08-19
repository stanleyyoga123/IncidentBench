from pathlib import Path

import numpy as np
import pandas as pd

from testbed.reporting.prometheus_metric_reader import PrometheusMetricReader

from .timebase import first_chaos_window


IMPACT_RELATIVE_THRESHOLD = 0.2


def metric_impact(run_folder: Path, metadata: dict, origin: float | None) -> dict:
    window = first_chaos_window(metadata)
    if window is None or origin is None:
        return {"observed": False, "reason": "no chaos window", "signals": {}}
    reader = PrometheusMetricReader()
    signals = {}
    observed = False
    checks = (
        ("deployment_cpu_usage", False),
        ("response_time_p95_seconds", False),
        ("http_5xx_rate", False),
        ("traffic_rps", True),
    )
    for name, invert in checks:
        frame = reader.read_all(run_folder, name)
        baseline = _mean(frame, frame["timestamp"] < origin) if not frame.empty else np.nan
        chaos = (
            _mean(
                frame,
                (frame["timestamp"] >= window.start) & (frame["timestamp"] <= window.end),
            )
            if not frame.empty
            else np.nan
        )
        diverged = _diverges(baseline, chaos, invert=invert)
        signals[name] = {
            "baseline": _json_float(baseline),
            "chaos": _json_float(chaos),
            "diverged": diverged,
        }
        observed = observed or diverged
    return {"observed": observed, "reason": None, "signals": signals}


def _mean(frame: pd.DataFrame, mask: pd.Series) -> float:
    selected = frame.loc[mask]
    if selected.empty:
        return np.nan
    return float(selected.groupby("timestamp")["value"].sum().mean())


def _diverges(baseline: float, chaos: float, *, invert: bool) -> bool:
    if pd.isna(baseline) or pd.isna(chaos):
        return False
    if baseline == 0:
        return abs(chaos) > 1e-9
    delta = (chaos - baseline) / abs(baseline)
    if invert:
        return delta <= -IMPACT_RELATIVE_THRESHOLD
    return delta >= IMPACT_RELATIVE_THRESHOLD


def _json_float(value: float) -> float | None:
    if pd.isna(value):
        return None
    return float(value)
