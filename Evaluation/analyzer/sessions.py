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
    "stress-cpu": (
        "stress-cpu",
        "stresschaos",
        "cpu stress",
        "stress cpu",
        "cpu hog",
        "cpu burn",
        "injected cpu",
    ),
    "delay": (
        "network delay",
        "network latency",
        "network degradation",
        "network path degradation",
        "network-induced performance degradation",
        "overlay network latency",
        "inter-node rtt",
        "elevated rtt",
        "netem delay",
        "delay fault",
        "delayed node",
        "delayed service",
        "injected delay",
    ),
    "loss": (
        "packet loss",
        "packet-loss",
        "network loss",
        "netem loss",
        "loss fault",
        "injected loss",
    ),
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
    remediation = load_json_list(folder / "remediation_run.json")
    remediation_sessions = load_json_list(folder / "remediation_session.json")
    details = {
        str(item.get("remediation_job_id")): item
        for item in remediation_sessions
        if isinstance(item, dict) and item.get("remediation_job_id")
    }
    remediation = [
        _merge_remediation_session(item, details.get(str(item.get("id"))))
        if isinstance(item, dict)
        else item
        for item in remediation
    ]
    return {
        "anomaly": load_json_list(folder / "anomaly.json"),
        "rca": load_json_list(folder / "rca_session.json"),
        "remediation": remediation,
        "remediation_session": remediation_sessions,
        "workflow": load_json_list(folder / "workflow.json"),
    }


def _merge_remediation_session(
    job: dict[str, Any], details: dict[str, Any] | None
) -> dict[str, Any]:
    if not details:
        return job
    merged = dict(job)
    if not merged.get("tool_calls"):
        merged["tool_calls"] = details.get("tool_calls") or []
    if not merged.get("artifacts"):
        merged["artifacts"] = details.get("artifacts") or []
    return merged


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


def match_injected_fault(
    job: dict[str, Any],
    ground_truth: dict[str, Any] | None,
    *,
    remediation: bool = False,
) -> str:
    faults = (ground_truth or {}).get("injected_faults") or []
    if not faults:
        return "no"
    haystack = (
        _remediation_haystack(job) if remediation else _rca_conclusion_haystack(job)
    )
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


def tool_call_evidence(
    calls: list[Any],
    *,
    max_calls: int = 4,
    argument_limit: int = 500,
    result_limit: int = 1000,
) -> list[dict[str, Any]]:
    """Return bounded, citable tool evidence rather than success flags alone."""
    calls = list(calls or [])
    if len(calls) > max_calls:
        head = max_calls // 2
        tail = max_calls - head
        selected = [
            *enumerate(calls[:head]),
            *enumerate(calls[-tail:], len(calls) - tail),
        ]
    else:
        selected = list(enumerate(calls))
    return [
        {
            "source_id": f"tool-{index + 1:03d}",
            "tool_name": call.get("tool_name"),
            "arguments": compact_result(call.get("arguments"), argument_limit),
            "result": compact_result(call.get("result"), result_limit),
        }
        for index, call in selected
        if isinstance(call, dict)
    ]


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


def _rca_conclusion_haystack(job: dict[str, Any]) -> str:
    result = job.get("result") or {}
    parts = [
        result.get("summary"),
        result.get("root_cause"),
        result.get("hypothesis"),
    ]
    return " ".join(str(part).lower() for part in parts if part)


def _remediation_haystack(job: dict[str, Any]) -> str:
    result = job.get("result") or {}
    parts = [
        result.get("summary"),
        json.dumps(result.get("changes") or [], default=str),
        json.dumps(result.get("verification") or [], default=str),
    ]
    for call in job.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        parts.extend(
            [
                call.get("tool_name"),
                json.dumps(call.get("arguments") or {}, default=str),
            ]
        )
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
    reference = str(fault.get("reference") or "").lower()
    if not action:
        if "cpu" in reference:
            action = "stress-cpu"
        elif "delay" in reference:
            action = "delay"
        elif "loss" in reference:
            action = "loss"
    alias_key = action
    if "delay" in action:
        alias_key = "delay"
    elif "loss" in action:
        alias_key = "loss"
    elif "bandwidth" in action or "rate" in action:
        alias_key = "bandwidth"
    elif "cpu" in action or "stress" in action:
        alias_key = "stress-cpu"
    tokens = list(_ACTION_ALIASES.get(alias_key, ()))
    if action:
        tokens.append(action.replace("-", " "))
        tokens.append(action)
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
