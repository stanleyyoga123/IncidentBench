import json
import re
from typing import Any

IMPACT_CLASSES = ("helped", "harmed", "no_impact")
TERMINAL_FAILURES = {"failed", "needs_review"}

_WORKER_RE = re.compile(
    r"worker(?:[-\s_]*node)?[-\s_]*(\d+)",
    re.IGNORECASE,
)
_ACTION_THEN_NODE = re.compile(
    r"(uncordon|cordon|drain)\s+(?:the\s+)?(?:node\s+)?"
    r"(worker(?:[-\s_]*node)?[-\s_]*\d+)",
    re.IGNORECASE,
)
_NODE_THEN_ACTION = re.compile(
    r"(worker(?:[-\s_]*node)?[-\s_]*\d+).{0,48}(uncordon|cordon|drain)",
    re.IGNORECASE,
)
_SCALE_RE = re.compile(
    r"\b(hpa|maxreplicas|replicas?|scale[d]?|patch deployment)\b",
    re.IGNORECASE,
)


def injected_targets(ground_truth: dict[str, Any] | None) -> set[str]:
    targets: set[str] = set()
    for fault in (ground_truth or {}).get("injected_faults") or []:
        inferred = fault.get("inferred_target")
        if inferred:
            normalized = _normalize_worker(str(inferred))
            if normalized:
                targets.add(normalized)
        reference = str(fault.get("reference") or "")
        normalized = _normalize_worker(reference)
        if normalized:
            targets.add(normalized)
    return targets


def classify_rca(
    labels: dict[str, Any],
    job: dict[str, Any],
    ground_truth: dict[str, Any] | None,
) -> tuple[str, str]:
    python_class, reason = _classify_rca_python(labels, job, ground_truth)
    return _maybe_llm(
        labels, python_class, reason, job, ground_truth, remediation=False
    )


def classify_remediation(
    labels: dict[str, Any],
    job: dict[str, Any],
    ground_truth: dict[str, Any] | None,
) -> tuple[str, str]:
    python_class, reason = _classify_remediation_python(labels, job, ground_truth)
    return _maybe_llm(
        labels, python_class, reason, job, ground_truth, remediation=True
    )


def session_highlights(
    rca: list[dict[str, Any]],
    remediation: list[dict[str, Any]],
) -> dict[str, Any]:
    items = _session_items(rca, remediation)
    helped = [item for item in items if item.get("impact_class") == "helped"]
    harmed = [item for item in items if item.get("impact_class") == "harmed"]
    best = max(helped, key=_best_key) if helped else None
    worst = max(harmed, key=_worst_key) if harmed else None
    return {
        "best": _highlight_view(best) if best else None,
        "worst": _highlight_view(worst) if worst else None,
    }


def session_categories(
    rca: list[dict[str, Any]],
    remediation: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped = {"helped": [], "harmed": [], "no_impact": []}
    for item in _session_items(rca, remediation):
        key = item.get("impact_class") if item.get("impact_class") in grouped else "no_impact"
        grouped[key].append(_highlight_view(item))
    return grouped


def _session_items(
    rca: list[dict[str, Any]],
    remediation: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items = []
    for item in rca or []:
        items.append({**item, "role": "rca"})
    for item in remediation or []:
        items.append({**item, "role": "remediation"})
    return items


def _best_key(item: dict[str, Any]) -> tuple[int, float]:
    addressed = 2 if item.get("role") == "remediation" and item.get("addressed_injection") == "yes" else 0
    remediator = 1 if item.get("role") == "remediation" else 0
    return (addressed + remediator, float(item.get("score") or 0.0))


def _worst_key(item: dict[str, Any]) -> tuple[int, float]:
    reason = str(item.get("impact_reason") or "").lower()
    uncordon = 1 if "uncordon" in reason else 0
    return (uncordon, -float(item.get("score") or 0.0))


def _highlight_view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": item.get("role"),
        "session_id": item.get("session_id"),
        "impact_class": item.get("impact_class"),
        "score": item.get("score"),
        "reason": item.get("impact_reason") or item.get("evidence") or "",
        "session_kind": item.get("session_kind"),
        "matched_injection": item.get("matched_injection"),
        "addressed_injection": item.get("addressed_injection"),
    }


def _maybe_llm(
    labels: dict[str, Any],
    python_class: str,
    reason: str,
    job: dict[str, Any],
    ground_truth: dict[str, Any] | None,
    *,
    remediation: bool,
) -> tuple[str, str]:
    llm_class = labels.get("impact_class")
    if _injected_node_action_override(job, ground_truth, remediation=remediation):
        return python_class, reason
    if llm_class in IMPACT_CLASSES:
        llm_class = str(llm_class)
        if "harmed" in {python_class, llm_class}:
            return "harmed", reason or str(labels.get("evidence") or "")
        if python_class == llm_class == "helped":
            return "helped", reason or str(labels.get("evidence") or "")
        return "no_impact", reason or str(labels.get("evidence") or "")
    return python_class, reason


def _injected_node_action_override(
    job: dict[str, Any],
    ground_truth: dict[str, Any] | None,
    *,
    remediation: bool,
) -> bool:
    injected = injected_targets(ground_truth)
    if not injected:
        return False
    haystack = (
        _remediation_classification_haystack(job)
        if remediation
        else _rca_classification_haystack(job)
    )
    for action, node in _node_actions(haystack):
        if node in injected and action in {"uncordon", "cordon", "drain"}:
            return True
    return False


def _classify_rca_python(
    labels: dict[str, Any],
    job: dict[str, Any],
    ground_truth: dict[str, Any] | None,
) -> tuple[str, str]:
    injected = injected_targets(ground_truth)
    actions = _node_actions(_rca_classification_haystack(job))
    matched = labels.get("matched_injection") == "yes" or labels.get("session_kind") == "true_positive"
    for action, node in actions:
        if action == "uncordon" and node in injected:
            return "harmed", f"recommended uncordoning the injected node {node}"
        if action in {"cordon", "drain"} and node not in injected:
            return "harmed", f"recommended draining healthy node {node}"
    if matched:
        for action, node in actions:
            if action in {"cordon", "drain"} and node in injected:
                return "helped", f"identified the injected fault and planned to drain {node}"
        target = next(iter(injected), "the injected locus")
        return "helped", f"identified the injected fault on {target}"
    if any(action in {"cordon", "drain", "uncordon"} and node in injected for action, node in actions):
        return "helped", "planned a node action on the injected locus"
    if any(action in {"cordon", "drain"} for action, _node in actions):
        node = next(node for action, node in actions if action in {"cordon", "drain"})
        return "harmed", f"recommended draining healthy node {node}"
    return "no_impact", "false-alarm RCA without an impactful mutation"


def _classify_remediation_python(
    labels: dict[str, Any],
    job: dict[str, Any],
    ground_truth: dict[str, Any] | None,
) -> tuple[str, str]:
    injected = injected_targets(ground_truth)
    haystack = _remediation_classification_haystack(job)
    actions = _node_actions(haystack)
    executed = _executed(job)
    for action, node in actions:
        if action == "uncordon" and node in injected:
            return "harmed", f"uncordoned the injected node {node}"
        if executed and action in {"cordon", "drain"} and node not in injected:
            return "harmed", f"drained healthy node {node}"
    if executed:
        for action, node in actions:
            if action in {"cordon", "drain"} and node in injected:
                return "helped", f"drained {node} to evacuate the injected fault"
        if labels.get("addressed_injection") == "yes":
            target = next(iter(injected), "the injected locus")
            return "helped", f"addressed the injected fault on {target}"
        if _SCALE_RE.search(haystack):
            return "no_impact", "scaled an unrelated workload"
        if any(action in {"cordon", "drain"} for action, _node in actions):
            node = next(node for action, node in actions if action in {"cordon", "drain"})
            return "harmed", f"drained healthy node {node}"
        return "no_impact", "live change did not target the injected fault"
    if labels.get("addressed_injection") == "yes":
        target = next(iter(injected), "the injected locus")
        return "helped", f"addressed the injected fault on {target}"
    return "no_impact", "no live mutation against the injected fault"


def _executed(job: dict[str, Any]) -> bool:
    status = str(job.get("status") or "")
    result = job.get("result")
    if status in TERMINAL_FAILURES and not result:
        return False
    if not result and not (job.get("tool_calls") or []):
        return False
    if status in TERMINAL_FAILURES:
        return bool(actions_in_result(result))
    return bool(result) or bool(job.get("tool_calls"))


def actions_in_result(result: Any) -> bool:
    encoded = json.dumps(result or {}, default=str).lower()
    return any(token in encoded for token in ("uncordon", "cordon", "drain", "kubectl"))


def _node_actions(haystack: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in _ACTION_THEN_NODE.finditer(haystack):
        action = _canonical_action(match.group(1))
        node = _normalize_worker(match.group(2))
        if action and node and (action, node) not in seen:
            seen.add((action, node))
            found.append((action, node))
    for match in _NODE_THEN_ACTION.finditer(haystack):
        action = _canonical_action(match.group(2))
        node = _normalize_worker(match.group(1))
        if action and node and (action, node) not in seen:
            seen.add((action, node))
            found.append((action, node))
    return found


def _canonical_action(token: str) -> str:
    text = token.lower()
    if "uncordon" in text:
        return "uncordon"
    if "drain" in text:
        return "drain"
    return "cordon"


def _normalize_worker(token: str | None) -> str | None:
    if not token:
        return None
    match = _WORKER_RE.search(token)
    if not match:
        return None
    return f"worker-node-{match.group(1)}"


def _rca_classification_haystack(job: dict[str, Any]) -> str:
    result = job.get("result") or {}
    plan = result.get("remediation_plan") or {}
    parts = [
        job.get("error"),
        job.get("status"),
        result.get("summary"),
        result.get("root_cause"),
        result.get("hypothesis"),
        result.get("action"),
        plan.get("action") if isinstance(plan, dict) else None,
        json.dumps(plan.get("targets") or [], default=str)
        if isinstance(plan, dict)
        else None,
    ]
    return " ".join(str(part).lower() for part in parts if part)


def _remediation_classification_haystack(job: dict[str, Any]) -> str:
    result = job.get("result") or {}
    plan = result.get("remediation_plan") or {}
    parts = [
        job.get("error"),
        job.get("status"),
        result.get("summary"),
        result.get("action"),
        json.dumps(result.get("changes") or [], default=str),
        plan.get("action") if isinstance(plan, dict) else None,
        json.dumps(plan.get("targets") or [], default=str)
        if isinstance(plan, dict)
        else None,
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
