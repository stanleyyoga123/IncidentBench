"""Render normalized run timelines and their machine-readable event tables."""

from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "evaluation-matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from .metrics import MetricDataset
from .timeline import RunTimeline


LANES = (
    ("chaos_active", "Chaos active"),
    ("anomaly_detected", "Anomaly detected"),
    ("rca_started", "RCA started"),
    ("rca_finished", "RCA finished"),
    ("remediation_started", "Remediation started"),
    ("ansible_check", "Ansible run (check)"),
    ("ansible_live", "Ansible run (live)"),
    ("ansible_run", "Ansible run"),
    ("remediation_finished", "Remediation finished"),
)

STYLES = {
    "anomaly_detected": ("#d62728", "D"),
    "rca_started": ("#9467bd", ">"),
    "rca_finished": ("#6f42c1", "o"),
    "remediation_started": ("#ff7f0e", ">"),
    "ansible_check": ("#17becf", "s"),
    "ansible_live": ("#1f77b4", "s"),
    "ansible_run": ("#4c78a8", "s"),
    "remediation_finished": ("#2ca02c", "o"),
}


def write_events_csv(timeline: RunTimeline, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "record_type", "kind", "occurred_at", "finished_at", "elapsed_minutes",
                "end_minutes", "label", "workflow_id", "job_id", "status",
            ),
        )
        writer.writeheader()
        for interval in timeline.intervals:
            writer.writerow(
                {
                    "record_type": "interval", "kind": interval.kind,
                    "occurred_at": interval.started_at.isoformat(),
                    "finished_at": interval.finished_at.isoformat(),
                    "elapsed_minutes": f"{interval.start_minutes:.6f}",
                    "end_minutes": f"{interval.end_minutes:.6f}", "label": interval.label,
                    "status": interval.status,
                }
            )
        for event in timeline.events:
            writer.writerow(
                {
                    "record_type": "event", "kind": event.kind,
                    "occurred_at": event.occurred_at.isoformat(),
                    "elapsed_minutes": f"{event.elapsed_minutes:.6f}", "label": event.label,
                    "workflow_id": event.workflow_id, "job_id": event.job_id, "status": event.status,
                }
            )


def _timeline_lanes(timeline: RunTimeline) -> list[tuple[str, str]]:
    present = {event.kind for event in timeline.events} | {interval.kind for interval in timeline.intervals}
    lanes = [(key, label) for key, label in LANES if key in present]
    if not lanes:
        raise ValueError(f"run {timeline.run_name} has no timeline events")
    return lanes


def _draw_timeline(axis, timeline: RunTimeline, *, compact: bool = False) -> None:
    lanes = _timeline_lanes(timeline)

    y_by_kind = {key: len(lanes) - index - 1 for index, (key, _) in enumerate(lanes)}

    for interval in timeline.intervals:
        if interval.kind not in y_by_kind:
            continue
        y = y_by_kind[interval.kind]
        width = max(0.0, interval.end_minutes - interval.start_minutes)
        axis.broken_barh([(interval.start_minutes, width)], (y - 0.27, 0.54),
                         facecolors="#ef4444", edgecolors="#991b1b", alpha=0.25, linewidth=1.0)

    for kind, _ in lanes:
        if kind == "chaos_active":
            continue
        values = [event.elapsed_minutes for event in timeline.events if event.kind == kind]
        if not values:
            continue
        color, marker = STYLES[kind]
        axis.scatter(values, [y_by_kind[kind]] * len(values), color=color, marker=marker,
                     s=30 if compact else 42, edgecolors="white", linewidths=0.55, zorder=3)

    axis.axvline(0, color="#374151", linewidth=1.0, alpha=0.8)
    axis.set_yticks([y_by_kind[key] for key, _ in lanes], [label for _, label in lanes])
    axis.set_ylim(-0.75, len(lanes) - 0.25)
    axis.set_xlabel("Elapsed time from run start (minutes)")
    axis.grid(axis="x", color="#d1d5db", linewidth=0.7, alpha=0.8)
    axis.grid(axis="y", color="#e5e7eb", linewidth=0.5, alpha=0.6)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.tick_params(axis="y", length=0)


def _timeline_legend(axis) -> None:

    handles = [
        Line2D([0], [0], color="#ef4444", linewidth=8, alpha=0.25, label="Chaos active window"),
        Line2D([0], [0], marker="s", color="none", markerfacecolor="#17becf",
               markeredgecolor="white", markersize=7, label="Ansible check mode"),
        Line2D([0], [0], marker="s", color="none", markerfacecolor="#1f77b4",
               markeredgecolor="white", markersize=7, label="Ansible live mode"),
    ]
    axis.legend(handles=handles, loc="upper right", frameon=False, fontsize=8)


def _draw_metric(axis, metric: MetricDataset, *, show_x_label: bool) -> None:
    color_map = plt.get_cmap("tab20")
    for index, series in enumerate(metric.series):
        axis.plot(series.elapsed_minutes, series.values, label=series.label,
                  linewidth=1.15, color=color_map(index % 20), alpha=0.95)
    axis.set_ylabel(metric.unit)
    if show_x_label:
        axis.set_xlabel("Elapsed time from run start (minutes)")
    axis.grid(color="#d1d5db", linewidth=0.65, alpha=0.75)
    axis.spines[["top", "right"]].set_visible(False)
    if len(metric.series) <= 14:
        axis.legend(loc="upper left", bbox_to_anchor=(1.005, 1.0), frameon=False, fontsize=7.5)


def render_timeline(timeline: RunTimeline, path: Path, *, dpi: int = 180) -> None:
    lanes = _timeline_lanes(timeline)
    height = max(4.2, 0.62 * len(lanes) + 2.0)
    fig, axis = plt.subplots(figsize=(13.2, height), constrained_layout=True)
    _draw_timeline(axis, timeline)
    axis.set_title(f"Evaluation timeline — {timeline.scenario}\n{timeline.run_name}", loc="left")
    _timeline_legend(axis)
    fig.savefig(path, dpi=dpi, metadata={"Creator": "Evaluation visualizer"})
    plt.close(fig)


def render_metric(metric: MetricDataset, timeline: RunTimeline, path: Path, *, dpi: int = 180) -> None:
    fig, axis = plt.subplots(figsize=(13.2, 5.6), constrained_layout=True)
    _draw_metric(axis, metric, show_x_label=True)
    axis.set_title(f"{metric.title} — {timeline.scenario}\n{timeline.run_name}", loc="left")
    fig.savefig(path, dpi=dpi, metadata={"Creator": "Evaluation visualizer"})
    plt.close(fig)


def render_metric_with_timeline(
    metric: MetricDataset, timeline: RunTimeline, path: Path, *, dpi: int = 180,
) -> None:
    lanes = _timeline_lanes(timeline)
    height = max(8.0, 5.0 + 0.46 * len(lanes))
    fig, (metric_axis, timeline_axis) = plt.subplots(
        2, 1, figsize=(13.2, height), sharex=True,
        gridspec_kw={"height_ratios": [3.2, max(2.4, 0.42 * len(lanes))]},
        constrained_layout=True,
    )
    _draw_metric(metric_axis, metric, show_x_label=False)
    for interval in timeline.intervals:
        metric_axis.axvspan(interval.start_minutes, interval.end_minutes, color="#ef4444", alpha=0.08,
                            linewidth=0)
    metric_axis.set_title(f"{metric.title} with incident timeline — {timeline.scenario}\n{timeline.run_name}", loc="left")
    _draw_timeline(timeline_axis, timeline, compact=True)
    fig.savefig(path, dpi=dpi, metadata={"Creator": "Evaluation visualizer"})
    plt.close(fig)
