from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from visualizer.cli import main
from visualizer.metrics import load_run_metrics
from visualizer.timeline import load_run_timeline


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _run(root: Path, name: str = "run-1") -> Path:
    run = root / name
    _write(
        run / "metadata.json",
        {
            "started_at": "2026-08-24T10:00:00+00:00",
            "scenario": {"name": "cpu-chaos"},
            "chaos_steps": [
                {
                    "index": 1,
                    "name": "cpu",
                    "chaos": ["cart-cpu"],
                    "idle": False,
                    "active_started_at": "2026-08-24T10:05:00+00:00",
                    "cleanup_started_at": "2026-08-24T10:15:00+00:00",
                    "status": "completed",
                }
            ],
        },
    )
    _write(
        run / "sessions/anomaly.json",
        [{"id": "event-row", "event_id": "event-123456", "detected_at": "2026-08-24T10:06:00+00:00",
          "workflow_id": "workflow-1", "name": "cartservice", "status": "claimed"}],
    )
    _write(
        run / "sessions/rca_session.json",
        [{"id": "rca-123456", "workflow_id": "workflow-1", "status": "succeeded",
          "started_at": "2026-08-24T10:07:00+00:00", "completed_at": "2026-08-24T10:08:00+00:00"}],
    )
    _write(
        run / "sessions/remediation_run.json",
        [{"id": "rem-123456", "workflow_id": "workflow-1", "status": "succeeded",
          "started_at": "2026-08-24T10:09:00+00:00", "completed_at": "2026-08-24T10:12:00+00:00"}],
    )
    _write(
        run / "sessions/remediation_session.json",
        [{
            "remediation_job_id": "rem-123456",
            "tool_calls": [
                {"tool_name": "prometheus", "created_at": "2026-08-24T10:09:15+00:00", "ok": True},
                {"tool_name": "remediator.run_ansible", "created_at": "2026-08-24T10:10:00+00:00",
                 "ok": True, "arguments": {"check": True}},
                {"tool_name": "remediator.run_ansible", "created_at": "2026-08-24T10:11:00+00:00",
                 "ok": True, "arguments": "{\"check\": false}"},
            ],
        }],
    )
    _write(
        run / "metrics/traffic_rps.json",
        {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {"destination_workload": "cartservice"},
                        "values": [[1787565660, "100"], [1787565720, "105"]],
                    },
                    {
                        "metric": {"destination_workload": "frontend"},
                        "values": [[1787565660, "80"], [1787565720, "bad"]],
                    },
                ]
            },
        },
    )
    _write(run / "metrics/metrics.json", {"summary": "not a query-range metric"})
    return run


def test_load_run_timeline_extracts_elapsed_events_and_ansible_modes(tmp_path: Path) -> None:
    timeline = load_run_timeline(_run(tmp_path))

    assert timeline.scenario == "cpu-chaos"
    assert [(interval.start_minutes, interval.end_minutes) for interval in timeline.intervals] == [(5.0, 15.0)]
    elapsed = {event.kind: event.elapsed_minutes for event in timeline.events}
    assert elapsed == {
        "anomaly_detected": 6.0,
        "rca_started": 7.0,
        "rca_finished": 8.0,
        "remediation_started": 9.0,
        "ansible_check": 10.0,
        "ansible_live": 11.0,
        "remediation_finished": 12.0,
    }
    assert not any(event.kind == "prometheus" for event in timeline.events)


def test_cli_renders_configurable_parent_input_and_csv(tmp_path: Path) -> None:
    input_path = tmp_path / "custom-input"
    _run(input_path, "first")
    _run(input_path, "second")
    output = tmp_path / "custom-output"

    main(["--input", str(input_path), "--output", str(output), "--format", "both", "--dpi", "72"])

    for name in ("first", "second"):
        run_output = output / "runs" / name
        assert (run_output / "timeline-only/timeline.png").stat().st_size > 0
        assert (run_output / "timeline-only/timeline.svg").stat().st_size > 0
        assert (run_output / "metrics-only/traffic_rps.png").stat().st_size > 0
        assert (run_output / "metrics-only/traffic_rps.svg").stat().st_size > 0
        assert (run_output / "metrics-with-timeline/traffic_rps.png").stat().st_size > 0
        assert (run_output / "metrics-with-timeline/traffic_rps.svg").stat().st_size > 0
        with (run_output / "timeline-only/events.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert {row["kind"] for row in rows} >= {"chaos_active", "anomaly_detected", "ansible_live"}
    assert "first" in (output / "report.md").read_text(encoding="utf-8")


def test_metric_loader_uses_run_origin_and_skips_bad_samples(tmp_path: Path) -> None:
    run = _run(tmp_path)
    timeline = load_run_timeline(run)

    metrics = load_run_metrics(run, timeline.origin)

    assert [metric.name for metric in metrics] == ["traffic_rps"]
    assert metrics[0].unit == "requests/s"
    assert [series.label for series in metrics[0].series] == ["cartservice", "frontend"]
    assert metrics[0].series[0].elapsed_minutes == pytest.approx((1.0, 2.0))
    assert metrics[0].series[0].values == (100.0, 105.0)
    assert metrics[0].series[1].values == (80.0,)


def test_cli_can_render_one_view_only(tmp_path: Path) -> None:
    run = _run(tmp_path / "input")
    output = tmp_path / "output"

    main(["--input", str(run), "--output", str(output), "--view", "timeline-only", "--format", "png"])

    run_output = output / "runs" / run.name
    assert (run_output / "timeline-only/timeline.png").is_file()
    assert not (run_output / "metrics-only").exists()
    assert not (run_output / "metrics-with-timeline").exists()


def test_missing_optional_sessions_produces_only_available_lanes(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _write(
        run / "metadata.json",
        {"started_at": "2026-08-24T10:00:00+00:00", "scenario": {"name": "only-chaos"},
         "chaos_steps": [{"index": 1, "chaos": ["delay"], "active_started_at": "2026-08-24T10:01:00+00:00",
                          "cleanup_started_at": "2026-08-24T10:02:00+00:00"}]},
    )

    timeline = load_run_timeline(run)

    assert timeline.events == ()
    assert len(timeline.intervals) == 1


def test_missing_origin_falls_back_to_earliest_event(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _write(run / "metadata.json", {"scenario": {"name": "fallback"}, "chaos_steps": []})
    _write(run / "sessions/anomaly.json", [{"detected_at": "2026-08-24T10:06:00Z"}])

    timeline = load_run_timeline(run)

    assert timeline.events[0].elapsed_minutes == 0
    assert timeline.warnings == ("metadata.started_at is missing; earliest event used as origin",)


def test_cli_rejects_missing_input(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="input path does not exist"):
        main(["--input", str(tmp_path / "missing")])
