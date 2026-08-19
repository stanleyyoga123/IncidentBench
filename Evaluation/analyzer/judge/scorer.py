from typing import Any

from analyzer.judge.classify import classify_rca, classify_remediation, session_categories, session_highlights
from analyzer.judge.schemas import (
    FALSE_ALARM_RUBRICS,
    LABEL_VALUES,
    MATCHED_VALUES,
    RCA_RUBRICS,
    REMEDIATION_RUBRICS,
)
from analyzer.sessions import match_injected_fault, tool_call_summaries

TERMINAL_FAILURES = {"failed", "needs_review"}
MAX_TOOL_PENALTY = 0.2
TOOL_PENALTY = 0.1
OPERATIONAL_DENOMINATOR = 10.0
HARMED_PENALTY = 0.15
SERIOUS_ERROR_KINDS = {"job_status", "job_error", "workflow"}
TRANSIENT_TOOL_ERRORS = (
    "http status error",
    "timeout",
    "timed out",
    "connection reset",
    "temporarily unavailable",
)

END_WEIGHTS = {
    "impact": 0.20,
    "rca": 0.30,
    "remediation": 0.30,
    "operational": 0.20,
}

RCA_BEST_WEIGHT = 0.80
RCA_FALSE_ALARM_WEIGHT = 0.20
RCA_MISS_WEIGHT = 0.40
REMEDIATION_BEST_WEIGHT = 0.80
REMEDIATION_REST_WEIGHT = 0.20


def label_value(label: str) -> float | None:
    if label == "not_applicable":
        return None
    return LABEL_VALUES.get(label)


def rubric_score(labels: dict[str, Any], names: tuple[str, ...]) -> float | None:
    values = []
    for name in names:
        value = label_value(str(labels.get(name, "not_applicable")))
        if value is not None:
            values.append(value)
    if not values:
        return None
    return sum(values) / len(values)


def apply_penalty(score: float | None, failed_tool_count: int, job_status: str | None) -> float:
    if job_status in TERMINAL_FAILURES:
        return 0.0
    if score is None:
        return 0.0
    deduction = min(MAX_TOOL_PENALTY, TOOL_PENALTY * max(0, failed_tool_count))
    return max(0.0, score - deduction)


def count_penalized_tools(job: dict[str, Any]) -> int:
    count = 0
    for call in tool_call_summaries(job.get("tool_calls") or []):
        if call["ok"] is not False:
            continue
        message = str(call.get("error") or "").lower()
        if any(token in message for token in TRANSIENT_TOOL_ERRORS):
            continue
        count += 1
    return count


def mean_or_none(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


def operational_failure_count(errors: dict[str, Any] | None) -> int:
    return sum(
        1
        for item in (errors or {}).get("errors") or []
        if item.get("kind") in SERIOUS_ERROR_KINDS
    )


def operational_health(failed_ops: int) -> float:
    return 1.0 - min(1.0, max(0, failed_ops) / OPERATIONAL_DENOMINATOR)


def rca_component_score(rca_results: list[dict[str, Any]]) -> float:
    true_positive = _raw_scores(
        item for item in rca_results if item.get("session_kind") == "true_positive"
    )
    false_alarm = _raw_scores(
        item for item in rca_results if item.get("session_kind") != "true_positive"
    )
    if true_positive:
        return RCA_BEST_WEIGHT * max(true_positive) + RCA_FALSE_ALARM_WEIGHT * (
            mean_or_none(false_alarm) or 0.0
        )
    mean_false = mean_or_none(false_alarm)
    return RCA_MISS_WEIGHT * mean_false if mean_false is not None else 0.0


def remediator_component_score(
    remediator_results: list[dict[str, Any]],
    rca_results: list[dict[str, Any]],
    remediator_invoked: bool,
    correctly_skipped: bool,
) -> float:
    if remediator_invoked:
        addressed = _raw_scores(
            item
            for item in remediator_results
            if item.get("addressed_injection") == "yes"
        )
        rest = _raw_scores(
            item
            for item in remediator_results
            if item.get("addressed_injection") != "yes"
        )
        if addressed:
            value = REMEDIATION_BEST_WEIGHT * max(addressed) + REMEDIATION_REST_WEIGHT * (
                mean_or_none(rest) or 0.0
            )
        else:
            value = mean_or_none(_raw_scores(remediator_results)) or 0.0
    elif correctly_skipped:
        value = rca_component_score(rca_results)
    else:
        value = 0.0
    if _any_harmed(rca_results, remediator_results):
        value = max(0.0, value - HARMED_PENALTY)
    return value


def remediator_slot_score(
    remediator_scores: list[float | None],
    rca_scores: list[float | None],
    remediator_invoked: bool,
    correctly_skipped: bool,
) -> float:
    if remediator_invoked:
        value = mean_or_none(remediator_scores)
        return value if value is not None else 0.0
    if correctly_skipped:
        value = mean_or_none(rca_scores)
        return value if value is not None else 0.0
    return 0.0


def end_score(
    *,
    impact_observed: bool,
    rca_score: float | None,
    remediator_score: float,
    operational: float,
) -> float:
    rca = rca_score if rca_score is not None else 0.0
    return (
        END_WEIGHTS["impact"] * (1.0 if impact_observed else 0.0)
        + END_WEIGHTS["rca"] * rca
        + END_WEIGHTS["remediation"] * remediator_score
        + END_WEIGHTS["operational"] * operational
    )


def merge_match(left: str | None, right: str | None) -> str:
    rank = {"yes": 2, "partial": 1, "no": 0}
    best = "no"
    for value in (left, right):
        key = value if value in rank else "no"
        if rank[key] > rank[best]:
            best = key
    return best


def normalize_rca_kind(labels: dict[str, Any]) -> str:
    if labels.get("matched_injection") == "yes":
        return "true_positive"
    kind = labels.get("session_kind")
    if kind in {"true_positive", "false_alarm"}:
        return kind
    rubrics = [str(labels.get(name, "not_applicable")) for name in RCA_RUBRICS]
    if rubrics and all(item == "not_applicable" for item in rubrics):
        return "false_alarm"
    return "false_alarm"


def score_rca_job(
    labels: dict[str, Any],
    job: dict[str, Any],
    failed_tools: int,
    ground_truth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scored = dict(labels)
    detected = match_injected_fault(job, ground_truth)
    scored["matched_injection"] = merge_match(
        detected, str(scored.get("matched_injection") or "no")
    )
    if scored["matched_injection"] == "yes":
        scored["localization"] = "correct"
        scored["session_kind"] = "true_positive"
    kind = normalize_rca_kind(scored)
    if kind == "false_alarm":
        _fill_false_alarm_defaults(scored, job)
    names = RCA_RUBRICS if kind == "true_positive" else FALSE_ALARM_RUBRICS
    values = []
    for name in names:
        value = label_value(str(scored.get(name, "not_applicable")))
        if value is not None:
            values.append(value)
    matched = MATCHED_VALUES.get(str(scored.get("matched_injection", "no")))
    if kind == "true_positive" and matched is not None:
        values.append(matched)
    raw = sum(values) / len(values) if values else None
    impact_class, impact_reason = classify_rca(scored, job, ground_truth)
    return {
        "session_id": labels.get("session_id") or str(job.get("id")),
        "session_kind": kind,
        "matched_injection": scored.get("matched_injection"),
        "impact_class": impact_class,
        "impact_reason": impact_reason,
        "labels": {
            name: scored.get(name)
            for name in (*RCA_RUBRICS, "false_alarm_recognition", "harmlessness")
        },
        "raw": raw,
        "score": apply_penalty(raw, failed_tools, job.get("status")),
        "evidence": labels.get("evidence"),
    }


def _fill_false_alarm_defaults(labels: dict[str, Any], job: dict[str, Any]) -> None:
    result = job.get("result") or {}
    required = result.get("remediation_required")
    recovered = str(result.get("incident_state") or "").lower() in {
        "recovered",
        "unconfirmed",
        "resolved",
        "absent",
    }
    dismissed = required is False or recovered
    harmful = required is True
    defaults = {
        "false_alarm_recognition": "correct" if dismissed else ("incorrect" if harmful else "partial"),
        "necessity": "correct" if not harmful else "incorrect",
        "harmlessness": "correct" if not harmful else "incorrect",
    }
    for name, value in defaults.items():
        if labels.get(name) in (None, "not_applicable"):
            labels[name] = value
    for name in ("evidence_quality", "grounding"):
        if labels.get(name) in (None, "not_applicable"):
            labels[name] = "partial" if result else "incorrect"


def score_remediation_job(
    labels: dict[str, Any],
    job: dict[str, Any],
    failed_tools: int,
    ground_truth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scored = dict(labels)
    detected = match_injected_fault(job, ground_truth)
    scored["addressed_injection"] = merge_match(
        detected, str(scored.get("addressed_injection") or "no")
    )
    if scored["addressed_injection"] == "yes":
        scored["target_correctness"] = "correct"
    values = []
    for name in REMEDIATION_RUBRICS:
        value = label_value(str(scored.get(name, "not_applicable")))
        if value is not None:
            values.append(value)
    addressed = MATCHED_VALUES.get(str(scored.get("addressed_injection", "no")))
    if addressed is not None:
        values.append(addressed)
    raw = sum(values) / len(values) if values else None
    impact_class, impact_reason = classify_remediation(scored, job, ground_truth)
    return {
        "session_id": labels.get("session_id") or str(job.get("id")),
        "addressed_injection": scored.get("addressed_injection"),
        "impact_class": impact_class,
        "impact_reason": impact_reason,
        "labels": {name: scored.get(name) for name in REMEDIATION_RUBRICS},
        "raw": raw,
        "score": apply_penalty(raw, failed_tools, job.get("status")),
        "evidence": labels.get("evidence"),
    }


def annotate_run_outcomes(
    rca_results: list[dict[str, Any]],
    rem_results: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    highlights = session_highlights(rca_results, rem_results)
    categories = session_categories(rca_results, rem_results)
    return highlights, categories


def _raw_scores(items) -> list[float]:
    values = []
    for item in items:
        raw = item.get("raw") if isinstance(item, dict) else item
        if raw is not None:
            values.append(float(raw))
    return values


def _any_harmed(*groups: list[dict[str, Any]]) -> bool:
    for group in groups:
        if any(item.get("impact_class") == "harmed" for item in group or []):
            return True
    return False
