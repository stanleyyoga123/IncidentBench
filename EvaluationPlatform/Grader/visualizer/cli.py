"""Command-line entry point for the archived-run timeline visualizer."""

from __future__ import annotations

import argparse
from pathlib import Path

from .metrics import load_run_metrics
from .render import render_metric, render_metric_with_timeline, render_timeline, write_events_csv
from .timeline import load_run_timeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render elapsed-time timelines for evaluation runs.")
    parser.add_argument("--input", type=Path, default=Path("results/result-3"),
                        help="run directory or directory containing runs (default: results/result-3)")
    parser.add_argument("--output", type=Path, default=Path("visualizations"),
                        help="output directory (default: visualizations)")
    parser.add_argument("--format", choices=("png", "svg", "both"), default="both",
                        help="plot format (default: both)")
    parser.add_argument(
        "--view", choices=("all", "metrics-only", "metrics-with-timeline", "timeline-only"),
        default="all", help="plot group to create (default: all)",
    )
    parser.add_argument("--dpi", type=int, default=180, help="PNG resolution (default: 180)")
    return parser


def _run_directories(input_path: Path) -> list[Path]:
    if (input_path / "metadata.json").is_file():
        return [input_path]
    if not input_path.is_dir():
        raise ValueError(f"input path does not exist or is not a directory: {input_path}")
    return sorted(path for path in input_path.iterdir() if path.is_dir() and (path / "metadata.json").is_file())


def _write_report(output: Path, records: list[dict[str, object]]) -> None:
    lines = ["# Evaluation visualizations", "", "| Run | Scenario | Metrics | Events | Chaos windows | Status |", "| --- | --- | ---: | ---: | ---: | --- |"]
    for record in records:
        lines.append(
            f"| {record['run']} | {record['scenario']} | {record['metrics']} | "
            f"{record['events']} | {record['intervals']} | {record['status']} |"
        )
    lines.extend(["", "Elapsed time is measured from `metadata.started_at`. Each run has separate "
                  "`metrics-only`, `metrics-with-timeline`, and `timeline-only` folders.", ""])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.dpi <= 0:
        raise SystemExit("--dpi must be positive")

    try:
        run_dirs = _run_directories(args.input)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if not run_dirs:
        raise SystemExit(f"no run directories containing metadata.json found under {args.input}")

    args.output.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    failures = 0
    for run_dir in run_dirs:
        run_output = args.output / "runs" / run_dir.name
        run_output.mkdir(parents=True, exist_ok=True)
        try:
            timeline = load_run_timeline(run_dir)
            metrics = load_run_metrics(run_dir, timeline.origin)
            formats = ("png", "svg") if args.format == "both" else (args.format,)
            views = ("metrics-only", "metrics-with-timeline", "timeline-only") if args.view == "all" else (args.view,)
            if "timeline-only" in views:
                destination = run_output / "timeline-only"
                destination.mkdir(parents=True, exist_ok=True)
                write_events_csv(timeline, destination / "events.csv")
                for file_format in formats:
                    render_timeline(timeline, destination / f"timeline.{file_format}", dpi=args.dpi)
            if "metrics-only" in views:
                destination = run_output / "metrics-only"
                destination.mkdir(parents=True, exist_ok=True)
                for metric in metrics:
                    for file_format in formats:
                        render_metric(metric, timeline, destination / f"{metric.name}.{file_format}", dpi=args.dpi)
            if "metrics-with-timeline" in views:
                destination = run_output / "metrics-with-timeline"
                destination.mkdir(parents=True, exist_ok=True)
                for metric in metrics:
                    for file_format in formats:
                        render_metric_with_timeline(
                            metric, timeline, destination / f"{metric.name}.{file_format}", dpi=args.dpi,
                        )
            warnings = list(timeline.warnings)
            if not metrics:
                warnings.append("no evaluable Prometheus metric files")
            status = "ok" if not warnings else "; ".join(warnings)
            records.append({"run": timeline.run_name, "scenario": timeline.scenario,
                            "metrics": len(metrics),
                            "events": len(timeline.events), "intervals": len(timeline.intervals),
                            "status": status})
            print(f"rendered {run_dir.name}: {len(metrics)} metrics, {len(timeline.events)} events")
        except (OSError, ValueError) as exc:
            failures += 1
            records.append({"run": run_dir.name, "scenario": "unknown", "metrics": 0, "events": 0,
                            "intervals": 0, "status": f"failed: {exc}"})
            print(f"failed {run_dir.name}: {exc}")

    _write_report(args.output, records)
    print(f"wrote visualizations for {len(records) - failures} run(s) to {args.output}")
    if failures:
        raise SystemExit(1)
