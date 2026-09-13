"""Load timestamped lifecycle events from one archived evaluation run."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TimelineEvent:
    kind: str
    occurred_at: datetime
    elapsed_minutes: float
    label: str
    workflow_id: str = ""
    job_id: str = ""
    status: str = ""


@dataclass(frozen=True)
class TimelineInterval:
    kind: str
    started_at: datetime
    finished_at: datetime
    start_minutes: float
    end_minutes: float
    label: str
    status: str = ""


@dataclass(frozen=True)
class RunTimeline:
    run_name: str
    scenario: str
    origin: datetime
    events: tuple[TimelineEvent, ...]
    intervals: tuple[TimelineInterval, ...]
    warnings: tuple[str, ...]


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        timestamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return timestamp.astimezone()
    return timestamp


def _rows(path: Path, warnings: list[str]) -> list[dict[str, Any]]:
    data = _read_json(path, [])
    if not isinstance(data, list):
        warnings.append(f"ignored non-list session file: {path.name}")
        return []
    return [row for row in data if isinstance(row, dict)]


def _arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _identifier(row: dict[str, Any], key: str = "id") -> str:
    value = row.get(key)
    return str(value) if value is not None else ""


def _short(identifier: str) -> str:
    return identifier[:8] if identifier else ""


def load_run_timeline(run_dir: Path) -> RunTimeline:
    """Return normalized events and chaos intervals for *run_dir*.

    The loader is intentionally read-only and tolerates missing optional session
    exports. A missing or invalid ``metadata.json`` remains a hard error because
    it is the run identity and preferred elapsed-time origin.
    """

    run_dir = Path(run_dir)
    metadata = _read_json(run_dir / "metadata.json", None)
    if not isinstance(metadata, dict):
        raise ValueError(f"missing or invalid metadata.json in {run_dir}")

    warnings: list[str] = []
    sessions = run_dir / "sessions"
    anomalies = _rows(sessions / "anomaly.json", warnings)
    rca_jobs = _rows(sessions / "rca_session.json", warnings)
    remediation_jobs = _rows(sessions / "remediation_run.json", warnings)
    remediation_sessions = _rows(sessions / "remediation_session.json", warnings)

    staged_events: list[tuple[str, datetime, str, str, str, str]] = []
    staged_intervals: list[tuple[str, datetime, datetime, str, str]] = []

    for step in metadata.get("chaos_steps", []):
        if not isinstance(step, dict) or step.get("idle") is True:
            continue
        start = _parse_timestamp(step.get("active_started_at"))
        finish = _parse_timestamp(step.get("cleanup_started_at"))
        if start is None:
            warnings.append(f"chaos step {step.get('index', '?')} has no active start")
            continue
        if finish is None:
            finish = _parse_timestamp(step.get("finished_at"))
        if finish is None or finish < start:
            warnings.append(f"chaos step {step.get('index', '?')} has no valid active end")
            continue
        references = step.get("chaos", [])
        if isinstance(references, list):
            label = ", ".join(str(item) for item in references) or str(step.get("name", "chaos"))
        else:
            label = str(step.get("name", "chaos"))
        staged_intervals.append(("chaos_active", start, finish, label, str(step.get("status", ""))))

    for row in anomalies:
        occurred = _parse_timestamp(row.get("detected_at"))
        if occurred is None:
            continue
        identifier = _identifier(row, "event_id") or _identifier(row)
        resource = str(row.get("name") or row.get("resource") or "anomaly")
        staged_events.append(
            ("anomaly_detected", occurred, f"{resource} {_short(identifier)}".strip(),
             _identifier(row, "workflow_id"), identifier, str(row.get("status", "")))
        )

    for row in rca_jobs:
        job_id = _identifier(row)
        workflow_id = _identifier(row, "workflow_id")
        for kind, field in (("rca_started", "started_at"), ("rca_finished", "completed_at")):
            occurred = _parse_timestamp(row.get(field))
            if occurred is not None:
                staged_events.append(
                    (kind, occurred, _short(job_id), workflow_id, job_id, str(row.get("status", "")))
                )

    for row in remediation_jobs:
        job_id = _identifier(row)
        workflow_id = _identifier(row, "workflow_id")
        for kind, field in (
            ("remediation_started", "started_at"),
            ("remediation_finished", "completed_at"),
        ):
            occurred = _parse_timestamp(row.get(field))
            if occurred is not None:
                staged_events.append(
                    (kind, occurred, _short(job_id), workflow_id, job_id, str(row.get("status", "")))
                )

    for session in remediation_sessions:
        remediation_job_id = _identifier(session, "remediation_job_id")
        tool_calls = session.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            continue
        for call in tool_calls:
            if not isinstance(call, dict) or call.get("tool_name") != "remediator.run_ansible":
                continue
            occurred = _parse_timestamp(call.get("created_at"))
            if occurred is None:
                continue
            check = _arguments(call.get("arguments")).get("check")
            kind = "ansible_check" if check is True else "ansible_live" if check is False else "ansible_run"
            outcome = "ok" if call.get("ok") is True else "failed" if call.get("ok") is False else "unknown"
            staged_events.append(
                (kind, occurred, f"{_short(remediation_job_id)} {outcome}".strip(), "",
                 remediation_job_id, outcome)
            )

    run_start = _parse_timestamp(metadata.get("started_at"))
    all_times = [item[1] for item in staged_events] + [item[1] for item in staged_intervals]
    if run_start is None:
        if not all_times:
            raise ValueError(f"run {run_dir.name} has no valid timestamps")
        run_start = min(all_times)
        warnings.append("metadata.started_at is missing; earliest event used as origin")

    def elapsed(timestamp: datetime) -> float:
        try:
            return (timestamp - run_start).total_seconds() / 60.0
        except TypeError as exc:
            raise ValueError(f"mixed timezone-aware and naive timestamps in {run_dir}") from exc

    events = tuple(
        TimelineEvent(kind, occurred, elapsed(occurred), label, workflow_id, job_id, status)
        for kind, occurred, label, workflow_id, job_id, status in sorted(staged_events, key=lambda item: item[1])
    )
    intervals = tuple(
        TimelineInterval(kind, start, finish, elapsed(start), elapsed(finish), label, status)
        for kind, start, finish, label, status in sorted(staged_intervals, key=lambda item: item[1])
    )
    scenario = metadata.get("scenario", {})
    scenario_name = str(scenario.get("name", "unknown")) if isinstance(scenario, dict) else "unknown"
    return RunTimeline(run_dir.name, scenario_name, run_start, events, intervals, tuple(warnings))

