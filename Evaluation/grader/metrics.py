from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
from statistics import median
from typing import Any


LOWER = "lower_is_better"
HIGHER = "higher_is_better"
STABLE = "stable_is_better"

METRIC_POLICIES: dict[str, str] = {
    "http_5xx_rate": LOWER,
    "response_time_p95_seconds": LOWER,
}

CORE_METRICS = (
    "response_time_p95_seconds",
    "http_5xx_rate",
)


def parse_timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def assess_change(before: float, after: float, policy: str, threshold: float) -> str:
    if not math.isfinite(before) or not math.isfinite(after):
        return "not_evaluable"
    if before == 0:
        if after == 0:
            return "stable"
        if policy == LOWER:
            return "improved" if after < 0 else "worsened"
        if policy == HIGHER:
            return "improved" if after > 0 else "worsened"
        return "worsened"
    change = (after - before) / abs(before)
    epsilon = 1e-12
    if policy == LOWER:
        if change <= -threshold + epsilon:
            return "improved"
        if change >= threshold - epsilon:
            return "worsened"
        return "stable"
    if policy == HIGHER:
        if change >= threshold - epsilon:
            return "improved"
        if change <= -threshold + epsilon:
            return "worsened"
        return "stable"
    if policy == STABLE:
        return "worsened" if abs(change) >= threshold - epsilon else "stable"
    raise ValueError(f"unknown metric policy: {policy}")


def relative_change(before: float | None, after: float | None) -> float | None:
    if before is None or after is None or before == 0:
        return None
    return (after - before) / abs(before)


def evaluate_metrics(
    run_folder: Path,
    completed_at: str | None,
    *,
    window_seconds: float = 300.0,
    threshold: float = 0.15,
) -> dict[str, Any]:
    if not completed_at:
        return _empty_evaluation("remediation job has no completed_at timestamp")
    try:
        anchor = parse_timestamp(completed_at)
    except (TypeError, ValueError):
        return _empty_evaluation("remediation completed_at timestamp is invalid")

    families: dict[str, Any] = {}
    for metric_name, policy in METRIC_POLICIES.items():
        families[metric_name] = _evaluate_family(
            run_folder / "metrics" / f"{metric_name}.json",
            metric_name,
            policy,
            anchor,
            window_seconds,
            threshold,
        )
    outcome, reason = metric_outcome(families)
    return {
        "outcome": outcome,
        "reason": reason,
        "anchor": completed_at,
        "anchor_epoch": anchor,
        "window_seconds": window_seconds,
        "threshold": threshold,
        "before_window": [anchor - window_seconds, anchor],
        "after_window": [anchor, anchor + window_seconds],
        "families": families,
    }


def metric_outcome(families: dict[str, Any]) -> tuple[str, str]:
    missing = [
        name
        for name in CORE_METRICS
        if (families.get(name) or {}).get("assessment") == "not_evaluable"
    ]
    if missing:
        return "not_evaluable", "core metric windows unavailable: " + ", ".join(missing)
    worsened = [
        name
        for name in CORE_METRICS
        if families[name].get("assessment") == "worsened"
    ]
    if worsened:
        return "not_good", "core metrics worsened: " + ", ".join(worsened)
    improved = [
        name for name, item in families.items() if item.get("assessment") == "improved"
    ]
    if not improved:
        return "not_good", "no metric family improved by the configured threshold"
    return "good", "core metrics did not worsen; improved: " + ", ".join(improved)


def _empty_evaluation(reason: str) -> dict[str, Any]:
    return {
        "outcome": "not_evaluable",
        "reason": reason,
        "anchor": None,
        "anchor_epoch": None,
        "window_seconds": None,
        "threshold": None,
        "before_window": None,
        "after_window": None,
        "families": {},
    }


def _evaluate_family(
    path: Path,
    metric_name: str,
    policy: str,
    anchor: float,
    window_seconds: float,
    threshold: float,
) -> dict[str, Any]:
    if not path.is_file():
        return _missing_family(metric_name, policy, "metric file is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return _missing_family(metric_name, policy, f"invalid metric JSON: {exc}")
    series_results: list[dict[str, Any]] = []
    for index, series in enumerate(payload.get("data", {}).get("result", [])):
        if not isinstance(series, dict):
            continue
        labels = series.get("metric") if isinstance(series.get("metric"), dict) else {}
        before_values: list[float] = []
        after_values: list[float] = []
        for raw in series.get("values") or []:
            if not isinstance(raw, list) or len(raw) < 2:
                continue
            try:
                timestamp, value = float(raw[0]), float(raw[1])
            except (TypeError, ValueError):
                continue
            if not math.isfinite(timestamp) or not math.isfinite(value):
                continue
            if anchor - window_seconds <= timestamp < anchor:
                before_values.append(value)
            elif anchor <= timestamp <= anchor + window_seconds:
                after_values.append(value)
        before = median(before_values) if before_values else None
        after = median(after_values) if after_values else None
        assessment = (
            assess_change(before, after, policy, threshold)
            if before is not None and after is not None
            else "not_evaluable"
        )
        series_results.append(
            {
                "series": _series_name(labels, index),
                "labels": labels,
                "before_median": before,
                "after_median": after,
                "relative_change": relative_change(before, after),
                "before_samples": len(before_values),
                "after_samples": len(after_values),
                "assessment": assessment,
            }
        )
    evaluable = [
        item
        for item in series_results
        if item["before_median"] is not None and item["after_median"] is not None
    ]
    if not evaluable:
        return {
            **_missing_family(metric_name, policy, "no series covers both windows"),
            "series": series_results,
        }
    family_before = median(item["before_median"] for item in evaluable)
    family_after = median(item["after_median"] for item in evaluable)
    return {
        "metric": metric_name,
        "policy": policy,
        "before_median": family_before,
        "after_median": family_after,
        "relative_change": relative_change(family_before, family_after),
        "assessment": assess_change(family_before, family_after, policy, threshold),
        "reason": None,
        "series": series_results,
    }


def _missing_family(metric_name: str, policy: str, reason: str) -> dict[str, Any]:
    return {
        "metric": metric_name,
        "policy": policy,
        "before_median": None,
        "after_median": None,
        "relative_change": None,
        "assessment": "not_evaluable",
        "reason": reason,
        "series": [],
    }


def _series_name(labels: dict[str, Any], index: int) -> str:
    for key in ("deployment", "destination_workload", "node"):
        if labels.get(key):
            return str(labels[key])
    if labels:
        return ",".join(f"{key}={labels[key]}" for key in sorted(labels))
    return f"series-{index + 1}"
