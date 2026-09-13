from datetime import datetime, timezone

from ...domain.scenario import ScenarioStep


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_step_result(step: ScenarioStep) -> dict:
    return {
        "index": step.index,
        "name": step.name,
        "chaos": list(step.chaos),
        "idle": step.idle,
        "duration": step.duration,
        "started_at": utc_now(),
        "active_started_at": None,
        "cleanup_started_at": None,
        "finished_at": None,
        "actual_active_duration_seconds": 0.0,
        "schedules": [],
        "error": None,
        "status": "running",
    }


def finish_step(result: dict, status: str) -> dict:
    result["status"] = status
    result["finished_at"] = utc_now()
    return result
