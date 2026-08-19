import json
import re
from pathlib import Path
from typing import Any


_SERVICE_NAMES = (
    "cartservice",
    "checkoutservice",
    "productcatalogservice",
    "recommendationservice",
    "paymentservice",
    "frontend",
    "emailservice",
    "currencyservice",
    "shippingservice",
    "adservice",
    "redis-cart",
)

_ACTION_ALIASES = {
    "stress-cpu": ("stress-cpu", "cpu stress", "stress cpu", "cpu hog", "cpu burn", "node cpu"),
    "delay": ("delay", "latency", "network delay"),
    "loss": ("packet loss", "packet-loss", "loss"),
    "bandwidth": ("bandwidth", "rate limit", "netem", "throttle"),
    "corrupt": ("corrupt", "corruption"),
    "duplicate": ("duplicate",),
}


def load_json_list(path: Path) -> list[Any]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text())
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    return [payload]


def load_sessions(run_folder: Path) -> dict[str, list[Any]]:
    folder = Path(run_folder) / "sessions"
    return {
        "anomaly": load_json_list(folder / "anomaly.json"),
        "rca": load_json_list(folder / "rca_session.json"),
        "remediation": load_json_list(folder / "remediation_run.json"),
        "remediation_session": load_json_list(folder / "remediation_session.json"),
        "workflow": load_json_list(folder / "workflow.json"),
    }


def scenario_context(metadata: dict) -> dict[str, Any]:
    scenario = metadata.get("scenario") or {}
    definitions = {
        item.get("reference"): item
        for item in metadata.get("chaos_definitions") or []
        if item.get("reference")
    }
    injected = []
    for step in scenario.get("steps") or metadata.get("chaos_steps") or []:
        references = [item for item in (step.get("chaos") or []) if item]
        if not references:
            continue
        for reference in references:
            definition = definitions.get(reference) or {}
            injected.append(
                {
                    "reference": reference,
                    "step_name": step.get("name"),
                    "child_type": definition.get("child_type"),
                    "action": definition.get("action"),
                    "inferred_target": inferred_target(reference),
                }
            )
    return {
        "scenario": scenario.get("name"),
        "placement": (metadata.get("placement") or {}).get("reference"),
        "agents_enabled": metadata.get("agents_enabled"),
        "ground_truth": {
            "injected_faults": injected,
            "rule": (
                "injected_faults is the only true incident. Detector anomalies "
                "are leads and may be symptoms or false alarms."
            ),
        },
        "chaos": [
            {
                "name": step.get("name"),
                "chaos": step.get("chaos") or [],
                "duration": step.get("duration") or step.get("configured_duration_seconds"),
            }
            for step in scenario.get("steps") or metadata.get("chaos_steps") or []
        ],
        "definitions": [
            {
                "reference": item.get("reference"),
                "child_type": item.get("child_type"),
                "action": item.get("action"),
            }
            for item in metadata.get("chaos_definitions") or []
        ],
    }


def inferred_target(reference: str) -> str | None:
    match = re.search(r"worker[-_]?(\d+)", reference or "", re.IGNORECASE)
    if match:
        return f"worker-node-{match.group(1)}"
    match = re.search("|".join(_SERVICE_NAMES), reference or "", re.IGNORECASE)
    if match:
        return match.group(0).lower()
    return None


def match_injected_fault(job: dict[str, Any], ground_truth: dict[str, Any] | None) -> str:
    faults = (ground_truth or {}).get("injected_faults") or []
    if not faults:
        return "no"
    haystack = _job_haystack(job)
    best = "no"
    for fault in faults:
        target_hit = _target_mentioned(haystack, fault)
        kind_hit = _kind_mentioned(haystack, fault)
        if target_hit and kind_hit:
            return "yes"
        if target_hit or kind_hit:
            best = "partial"
    return best


def compact_result(value: Any, limit: int = 8000) -> Any:
    encoded = json.dumps(value, default=str)
    if len(encoded) <= limit:
        return value
    return encoded[:limit] + "..."


def tool_call_summaries(calls: list[Any]) -> list[dict[str, Any]]:
    summaries = []
    for call in calls or []:
        result = call.get("result")
        ok = call.get("ok")
        if ok is None:
            ok = not (isinstance(result, dict) and result.get("ok") is False)
        summaries.append(
            {
                "tool_name": call.get("tool_name"),
                "ok": ok,
                "error": _tool_error_message(call),
            }
        )
    return summaries


def _job_haystack(job: dict[str, Any]) -> str:
    result = job.get("result") or {}
    plan = result.get("remediation_plan") or {}
    parts = [
        job.get("error"),
        result.get("summary"),
        result.get("root_cause"),
        result.get("incident_state"),
        result.get("hypothesis"),
        json.dumps(result.get("evidence") or [], default=str),
        json.dumps(plan, default=str),
        json.dumps(plan.get("targets") or [], default=str),
        plan.get("action"),
    ]
    return " ".join(str(part).lower() for part in parts if part)


def _target_mentioned(haystack: str, fault: dict[str, Any]) -> bool:
    candidates = [
        fault.get("inferred_target"),
        fault.get("reference"),
    ]
    reference = str(fault.get("reference") or "")
    match = re.search(r"worker[-_]?(\d+)", reference, re.IGNORECASE)
    if match:
        candidates.extend(
            [
                f"worker-node-{match.group(1)}",
                f"worker {match.group(1)}",
            ]
        )
    for candidate in candidates:
        if candidate and str(candidate).lower() in haystack:
            return True
    return False


def _kind_mentioned(haystack: str, fault: dict[str, Any]) -> bool:
    action = str(fault.get("action") or "").lower()
    child = str(fault.get("child_type") or "").lower()
    reference = str(fault.get("reference") or "").lower()
    tokens = list(_ACTION_ALIASES.get(action, ()))
    if action:
        tokens.append(action.replace("-", " "))
        tokens.append(action)
    if child:
        tokens.append(child.lower())
    if "cpu" in reference or action == "stress-cpu":
        tokens.extend(("cpu", "stress"))
    if "delay" in reference:
        tokens.append("delay")
    if "loss" in reference:
        tokens.append("loss")
    return any(token and token in haystack for token in tokens)


def _tool_error_message(call: dict[str, Any]) -> str | None:
    result = call.get("result")
    if isinstance(result, dict):
        if result.get("ok") is False:
            return str(result.get("error") or result.get("stderr") or result.get("message") or "tool failed")
        if result.get("error"):
            return str(result["error"])
    if call.get("ok") is False:
        return "tool failed"
    return None
