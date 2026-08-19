from pathlib import Path
from typing import Any
import json

import pandas as pd

from .sessions import load_sessions, tool_call_summaries


TERMINAL_JOB_FAILURES = {"failed", "needs_review"}
BENIGN_LOCUST_FAILURE_PCT = 1.0


def collect_errors(run_folder: Path, metadata: dict) -> dict[str, Any]:
    sessions = load_sessions(run_folder)
    items: list[dict[str, Any]] = []
    items.extend(_job_errors("rca", sessions["rca"]))
    items.extend(_job_errors("remediation", sessions["remediation"]))
    items.extend(_workflow_errors(sessions["workflow"]))
    items.extend(_metadata_errors(metadata))
    items.extend(_snapshot_errors(run_folder, metadata))
    locust = _locust_status(run_folder, metadata)
    agent_errors = [item for item in items if item.get("kind") != "load_generator_stop"]
    return {
        "errors": items,
        "agent_error_count": len(agent_errors),
        "failed_tool_count": sum(1 for item in items if item.get("kind") == "tool_failure"),
        "locust": locust,
    }


def _job_errors(kind: str, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for job in jobs:
        job_id = str(job.get("id") or job.get("remediation_job_id") or "")
        status = job.get("status")
        if status in TERMINAL_JOB_FAILURES:
            items.append(
                {
                    "kind": "job_status",
                    "source": kind,
                    "job_id": job_id,
                    "status": status,
                    "message": _error_message(job.get("error")) or f"{kind} job {status}",
                }
            )
        elif job.get("error"):
            items.append(
                {
                    "kind": "job_error",
                    "source": kind,
                    "job_id": job_id,
                    "status": status,
                    "message": _error_message(job.get("error")),
                }
            )
        for call in job.get("tool_calls") or []:
            summary = tool_call_summaries([call])[0]
            if summary["ok"] is False or summary["error"]:
                if summary["ok"] is False:
                    items.append(
                        {
                            "kind": "tool_failure",
                            "source": kind,
                            "job_id": job_id,
                            "tool_name": summary["tool_name"],
                            "message": summary["error"] or "tool failed",
                        }
                    )
    return items


def _workflow_errors(workflows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for workflow in workflows:
        status = workflow.get("status")
        if status in TERMINAL_JOB_FAILURES or workflow.get("error"):
            items.append(
                {
                    "kind": "workflow",
                    "source": "workflow",
                    "job_id": str(workflow.get("id") or ""),
                    "status": status,
                    "message": _error_message(workflow.get("error")) or f"workflow {status}",
                }
            )
    return items


def _metadata_errors(metadata: dict) -> list[dict[str, Any]]:
    items = []
    for step in metadata.get("chaos_steps") or []:
        status = step.get("status")
        if status and status != "completed":
            items.append(
                {
                    "kind": "chaos_step",
                    "source": "metadata",
                    "job_id": str(step.get("index")),
                    "status": status,
                    "message": step.get("error") or f"chaos step {status}",
                }
            )
    if metadata.get("chaos_final_cleanup_error"):
        items.append(
            {
                "kind": "cleanup",
                "source": "metadata",
                "message": str(metadata["chaos_final_cleanup_error"]),
            }
        )
    for phase in metadata.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        returncode = phase.get("returncode")
        if returncode not in (None, 0):
            items.append(
                {
                    "kind": "phase",
                    "source": "metadata",
                    "job_id": phase.get("name"),
                    "status": phase.get("status"),
                    "message": f"phase {phase.get('name')} returncode {returncode}",
                }
            )
    locust_code = (metadata.get("loadgenerator") or {}).get("returncode")
    if locust_code not in (None, 0):
        items.append(
            {
                "kind": "load_generator_stop",
                "source": "loadgenerator",
                "status": str(locust_code),
                "message": f"locust returncode {locust_code}",
            }
        )
    return items


def _snapshot_errors(run_folder: Path, metadata: dict) -> list[dict[str, Any]]:
    items = []
    snapshots = list(metadata.get("snapshots") or [])
    snapshot_root = Path(run_folder) / "snapshots"
    if snapshot_root.is_dir():
        for path in snapshot_root.glob("*/snapshot.json"):
            snapshots.append(json.loads(path.read_text()))
    seen = set()
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        label = snapshot.get("label") or "snapshot"
        for command in snapshot.get("commands") or []:
            if command.get("returncode") in (None, 0):
                continue
            key = (label, command.get("name"), command.get("returncode"))
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "kind": "snapshot_command",
                    "source": "snapshot",
                    "job_id": f"{label}/{command.get('name')}",
                    "status": str(command.get("returncode")),
                    "message": command.get("stderr")
                    or f"{command.get('name')} returncode {command.get('returncode')}",
                }
            )
    return items


def _locust_status(run_folder: Path, metadata: dict) -> dict[str, Any]:
    returncode = (metadata.get("loadgenerator") or {}).get("returncode")
    failure_pct = _locust_failure_pct(run_folder)
    benign = False
    if returncode not in (None, 0):
        benign = failure_pct is not None and failure_pct <= BENIGN_LOCUST_FAILURE_PCT
    return {
        "returncode": returncode,
        "failure_pct": failure_pct,
        "benign_stop": benign,
    }


def _locust_failure_pct(run_folder: Path) -> float | None:
    paths = sorted((Path(run_folder) / "loadgenerator").glob("*_stats.csv"))
    if not paths:
        return None
    frame = pd.read_csv(paths[0])
    if frame.empty:
        return None
    if "Name" not in frame.columns:
        row = frame.iloc[-1]
    else:
        aggregated = frame[frame["Name"].astype(str).isin(["Aggregated", "Total"])]
        row = aggregated.iloc[-1] if not aggregated.empty else frame.iloc[-1]
    requests = pd.to_numeric(row.get("Request Count"), errors="coerce")
    failures = pd.to_numeric(row.get("Failure Count"), errors="coerce")
    if pd.isna(requests) or requests == 0 or pd.isna(failures):
        return None
    return 100.0 * float(failures) / float(requests)


def _error_message(error: Any) -> str | None:
    if not error:
        return None
    if isinstance(error, dict):
        return str(error.get("message") or error.get("type") or error)
    return str(error)
