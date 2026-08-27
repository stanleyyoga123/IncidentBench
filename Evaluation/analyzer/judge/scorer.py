from typing import Any

from analyzer.judge.classify import classify_rca, classify_remediation, session_categories, session_highlights
from analyzer.judge.schemas import (
    ATTEMPT_CLASSES,
    FALSE_ALARM_RUBRICS,
    LABEL_VALUES,
    MATCHED_VALUES,
    RCA_RUBRICS,
    REMEDIATION_RUBRICS,
)
from analyzer.sessions import match_injected_fault, tool_call_evidence, tool_call_summaries

TERMINAL_FAILURES = {"failed", "needs_review"}
OPERATIONAL_DENOMINATOR = 10.0
SERIOUS_ERROR_KINDS = {"job_status", "job_error", "workflow"}
TRANSIENT_TOOL_ERRORS = (
    "http status error",
    "timeout",
    "timed out",
    "connection reset",
    "temporarily unavailable",
)

END_WEIGHTS = {
    "impact": 0.00,
    "rca": 0.40,
    "remediation": 0.40,
    "operational": 0.20,
}

RCA_INJECTION_WEIGHT = 0.40
RCA_SESSION_WEIGHT = 0.60


def label_value(label: str) -> float | None:
    if label == "not_applicable":
        return 0.0
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
    """Fail terminal jobs, but do not penalize exploratory tool errors."""
    if job_status in TERMINAL_FAILURES:
        return 0.0
    if score is None:
        return 0.0
    return max(0.0, score)


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
    """Balance injection detection with quality across every detector lead."""
    if not rca_results:
        return 0.0
    session_accuracy = mean_or_none(_scores(rca_results)) or 0.0
    injection_quality = max(
        (
            float(item.get("score") or 0.0)
            * MATCHED_VALUES.get(
                str(item.get("matched_injection") or "no"), 0.0
            )
            for item in rca_results
        ),
        default=0.0,
    )
    return (
        RCA_INJECTION_WEIGHT * injection_quality
        + RCA_SESSION_WEIGHT * session_accuracy
    )


def remediator_component_score(
    remediator_results: list[dict[str, Any]],
    rca_results: list[dict[str, Any]],
    remediator_invoked: bool,
    correctly_skipped: bool,
) -> float:
    if remediator_invoked:
        value = mean_or_none(_scores(remediator_results)) or 0.0
    elif correctly_skipped:
        value = rca_component_score(rca_results)
    else:
        value = 0.0
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
        END_WEIGHTS["rca"] * rca
        + END_WEIGHTS["remediation"] * remediator_score
        + END_WEIGHTS["operational"] * operational
    )


def reconcile_match(detected: str | None, judged: str | None) -> str:
    """Use the more conservative result when lexical and LLM judgments disagree."""
    rank = {"yes": 2, "partial": 1, "no": 0}
    left = detected if detected in rank else "no"
    right = judged if judged in rank else "no"
    return left if rank[left] <= rank[right] else right


def normalize_rca_kind(labels: dict[str, Any]) -> str:
    if labels.get("matched_injection") == "yes":
        return "true_positive"
    if labels.get("matched_injection") == "no":
        return "false_alarm"
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
    judged_match = str(scored.get("matched_injection") or "no")
    if (ground_truth or {}).get("reference_answer"):
        scored["matched_injection"] = (
            judged_match if judged_match in MATCHED_VALUES else "no"
        )
    else:
        scored["matched_injection"] = reconcile_match(detected, judged_match)
    if scored["matched_injection"] == "yes":
        scored["localization"] = "correct"
        scored["session_kind"] = "true_positive"
    kind = normalize_rca_kind(scored)
    if kind == "false_alarm":
        _fill_false_alarm_defaults(scored, job)
    evidence_refs = _enforce_rca_evidence(scored, job)
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
    attempt_judged = (
        labels.get("attempt_class") in ATTEMPT_CLASSES
        and not labels.get("_judge_error")
    )
    attempt_class = (
        _rca_attempt_class(scored, evidence_refs, impact_class)
        if attempt_judged
        else None
    )
    comparison_judged = (
        labels.get("matched_injection") in MATCHED_VALUES
        and not labels.get("_judge_error")
    )
    system_harm = impact_class == "harmed"
    ground_truth_match = (
        scored.get("matched_injection") == "yes" and not system_harm
    )
    return {
        "session_id": labels.get("session_id") or str(job.get("id")),
        "session_kind": kind,
        "matched_injection": scored.get("matched_injection"),
        "impact_class": impact_class,
        "impact_reason": impact_reason,
        "attempt_class": attempt_class,
        "attempt_judged": attempt_judged,
        "efficiency_credit": _attempt_credit(
            attempt_class, attempt_judged, impact_class
        ),
        "ground_truth_match": ground_truth_match,
        "comparison_judged": comparison_judged,
        "accuracy": 1.0 if ground_truth_match else 0.0,
        "system_harm": system_harm,
        "layer_score": _layer_score(ground_truth_match, system_harm),
        "labels": {
            name: scored.get(name)
            for name in (*RCA_RUBRICS, "false_alarm_recognition", "harmlessness")
        },
        "raw": raw,
        "score": apply_penalty(raw, failed_tools, job.get("status")),
        "evidence": labels.get("evidence"),
        "evidence_refs": evidence_refs,
        "confidence": labels.get("confidence") or "low",
        "judge_error": labels.get("_judge_error"),
        "led_to_success": False,
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
    linked_rca: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scored = dict(labels)
    detected = match_injected_fault(job, ground_truth, remediation=True)
    if (
        detected == "partial"
        and scored.get("addressed_injection") == "yes"
        and (linked_rca or {}).get("attempt_judged")
        and (linked_rca or {}).get("attempt_class") == "targeted"
    ):
        detected = "yes"
    judged_match = str(scored.get("addressed_injection") or "no")
    if (ground_truth or {}).get("reference_answer"):
        scored["addressed_injection"] = (
            judged_match if judged_match in MATCHED_VALUES else "no"
        )
    else:
        scored["addressed_injection"] = reconcile_match(detected, judged_match)
    if scored["addressed_injection"] == "yes":
        scored["target_correctness"] = "correct"
    evidence_refs = _enforce_remediation_evidence(scored, job)
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
    attempt_judged = (
        labels.get("attempt_class") in ATTEMPT_CLASSES
        and not labels.get("_judge_error")
    )
    attempt_class = (
        _remediation_attempt_class(
            scored,
            evidence_refs,
            impact_class,
            linked_rca,
        )
        if attempt_judged
        else None
    )
    recovery_refs = _valid_recovery_refs(labels, job)
    recovery_proven = (
        labels.get("recovery_proven") == "yes" and bool(recovery_refs)
    )
    fix_outcome = (
        "success"
        if _successful_fix(
            scored,
            job,
            attempt_class,
            impact_class,
            recovery_proven,
        )
        else "unsuccessful"
    )
    comparison_judged = (
        labels.get("addressed_injection") in MATCHED_VALUES
        and not labels.get("_judge_error")
    )
    system_harm = impact_class == "harmed"
    ground_truth_match = (
        scored.get("addressed_injection") == "yes" and not system_harm
    )
    score = apply_penalty(raw, failed_tools, job.get("status"))
    if impact_class == "harmed":
        score = 0.0
    return {
        "session_id": labels.get("session_id") or str(job.get("id")),
        "addressed_injection": scored.get("addressed_injection"),
        "impact_class": impact_class,
        "impact_reason": impact_reason,
        "attempt_class": attempt_class,
        "attempt_judged": attempt_judged,
        "efficiency_credit": _attempt_credit(
            attempt_class, attempt_judged, impact_class
        ),
        "ground_truth_match": ground_truth_match,
        "comparison_judged": comparison_judged,
        "accuracy": 1.0 if ground_truth_match else 0.0,
        "system_harm": system_harm,
        "layer_score": _layer_score(ground_truth_match, system_harm),
        "labels": {name: scored.get(name) for name in REMEDIATION_RUBRICS},
        "raw": raw,
        "score": score,
        "evidence": labels.get("evidence"),
        "evidence_refs": evidence_refs,
        "confidence": labels.get("confidence") or "low",
        "status": job.get("status"),
        "judge_error": labels.get("_judge_error"),
        "rca_session_id": str(job.get("rca_job_id") or ""),
        "recovery_proven": recovery_proven,
        "recovery_evidence_refs": recovery_refs,
        "fix_outcome": fix_outcome,
    }


def accuracy_metrics(remediation_results: list[dict[str, Any]]) -> dict[str, Any]:
    if any(item.get("fix_outcome") == "success" for item in remediation_results):
        return {"accuracy": 1.0, "accuracy_complete": True}
    if any(
        not item.get("attempt_judged")
        and item.get("status") not in TERMINAL_FAILURES
        for item in remediation_results
    ):
        return {"accuracy": None, "accuracy_complete": False}
    return {"accuracy": 0.0, "accuracy_complete": True}


def ground_truth_metrics(
    rca_results: list[dict[str, Any]],
    remediation_results: list[dict[str, Any]],
) -> dict[str, Any]:
    rca = _role_ground_truth_metrics(rca_results)
    remediation = _role_ground_truth_metrics(remediation_results)
    complete = rca["complete"] and remediation["complete"]
    if rca["accuracy"] == 1.0 and remediation["accuracy"] == 1.0:
        accuracy = 1.0
        complete = True
    elif not complete:
        accuracy = None
    else:
        accuracy = 0.0
    attempts = [*rca_results, *remediation_results]
    judged = [item for item in attempts if item.get("comparison_judged")]
    layer_scores = [float(item.get("layer_score") or 0.0) for item in judged]
    return {
        "accuracy": accuracy,
        "accuracy_complete": complete,
        "rca_accuracy": rca["accuracy"],
        "remediation_accuracy": remediation["accuracy"],
        "ground_truth_score": (
            sum(layer_scores) / len(layer_scores) if layer_scores else None
        ),
        "safety_score": (
            sum(not item.get("system_harm") for item in judged) / len(judged)
            if judged
            else None
        ),
        "comparison_coverage": (
            len(judged) / len(attempts) if attempts else 1.0
        ),
        "ground_truth_match_count": sum(
            bool(item.get("ground_truth_match")) for item in judged
        ),
        "harmful_attempt_count": sum(
            bool(item.get("system_harm")) for item in judged
        ),
    }


def _role_ground_truth_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    judged = [item for item in items if item.get("comparison_judged")]
    matched = any(item.get("ground_truth_match") for item in judged)
    complete = len(judged) == len(items)
    if matched:
        accuracy = 1.0
        complete = True
    elif complete:
        accuracy = 0.0
    else:
        accuracy = None
    return {
        "accuracy": accuracy,
        "complete": complete,
    }


def _layer_score(ground_truth_match: bool, system_harm: bool) -> float:
    if ground_truth_match:
        return 1.0
    return 0.0 if system_harm else 0.5


def efficiency_metrics(
    rca_results: list[dict[str, Any]],
    remediation_results: list[dict[str, Any]],
) -> dict[str, Any]:
    attempts = [*rca_results, *remediation_results]
    judged = [item for item in attempts if item.get("attempt_judged")]
    total = len(attempts)
    counts = {
        name: sum(item.get("attempt_class") == name for item in judged)
        for name in ATTEMPT_CLASSES
    }
    credits = [float(item.get("efficiency_credit") or 0.0) for item in judged]
    return {
        "efficiency": sum(credits) / len(judged) if judged else None,
        "efficiency_complete": len(judged) == total,
        "attempt_coverage": len(judged) / total if total else 1.0,
        "judged_attempt_count": len(judged),
        "total_attempt_count": total,
        "targeted_attempt_count": counts["targeted"],
        "side_effect_attempt_count": counts["side_effect"],
        "efficiency_false_alarm_count": counts["false_alarm"],
    }


def annotate_run_outcomes(
    rca_results: list[dict[str, Any]],
    rem_results: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    highlights = session_highlights(rca_results, rem_results)
    categories = session_categories(rca_results, rem_results)
    return highlights, categories


def _scores(items) -> list[float]:
    values = []
    for item in items:
        score = item.get("score") if isinstance(item, dict) else item
        if score is not None:
            values.append(float(score))
    return values


def _valid_evidence_refs(labels: dict[str, Any], job: dict[str, Any]) -> list[str]:
    available = {
        item["source_id"] for item in tool_call_evidence(job.get("tool_calls") or [])
    }
    refs = labels.get("evidence_refs") or []
    if not isinstance(refs, list):
        return []
    return [str(ref) for ref in refs if str(ref) in available]


def _enforce_rca_evidence(labels: dict[str, Any], job: dict[str, Any]) -> list[str]:
    refs = _valid_evidence_refs(labels, job)
    if refs:
        return refs
    if labels.get("evidence_quality") == "correct":
        labels["evidence_quality"] = "partial"
    if labels.get("grounding") in {"correct", "partial"}:
        labels["grounding"] = "incorrect"
    return []


def _enforce_remediation_evidence(
    labels: dict[str, Any], job: dict[str, Any]
) -> list[str]:
    refs = _valid_evidence_refs(labels, job)
    if refs:
        return refs
    for name in ("execution_discipline", "verification"):
        if labels.get(name) == "correct":
            labels[name] = "partial"
    return []


def _rca_attempt_class(
    labels: dict[str, Any],
    evidence_refs: list[str],
    impact_class: str,
) -> str:
    claimed = labels.get("attempt_class")
    grounded = (
        bool(evidence_refs)
        and labels.get("evidence_quality") in {"correct", "partial"}
        and labels.get("grounding") in {"correct", "partial"}
    )
    if claimed == "targeted" and labels.get("matched_injection") == "yes" and grounded:
        return "targeted"
    if (
        claimed == "side_effect"
        and labels.get("matched_injection") != "yes"
        and grounded
        and impact_class != "harmed"
    ):
        return "side_effect"
    return "false_alarm"


def _remediation_attempt_class(
    labels: dict[str, Any],
    evidence_refs: list[str],
    impact_class: str,
    linked_rca: dict[str, Any] | None,
) -> str:
    claimed = labels.get("attempt_class")
    if (
        claimed == "targeted"
        and labels.get("addressed_injection") == "yes"
        and labels.get("target_correctness") == "correct"
        and evidence_refs
    ):
        return "targeted"
    if (
        claimed == "side_effect"
        and evidence_refs
        and impact_class != "harmed"
        and labels.get("safety") in {"correct", "partial"}
        and (linked_rca or {}).get("attempt_judged")
        and (linked_rca or {}).get("attempt_class") == "side_effect"
    ):
        return "side_effect"
    return "false_alarm"


def _attempt_credit(
    attempt_class: str | None,
    attempt_judged: bool,
    impact_class: str,
) -> float | None:
    if not attempt_judged:
        return None
    if impact_class == "harmed":
        return 0.0
    return 1.0 if attempt_class in {"targeted", "side_effect"} else 0.0


def _valid_recovery_refs(
    labels: dict[str, Any], job: dict[str, Any]
) -> list[str]:
    calls = list(job.get("tool_calls") or [])
    mutation_indices = [
        index for index, call in enumerate(calls) if _is_live_mutation(call)
    ]
    if not mutation_indices:
        return []
    last_mutation = max(mutation_indices)
    available = {
        item["source_id"]: item
        for item in tool_call_evidence(calls)
    }
    refs = labels.get("recovery_evidence_refs") or []
    if not isinstance(refs, list):
        return []
    return [
        str(ref)
        for ref in refs
        if str(ref) in available
        and _source_index(str(ref)) > last_mutation
        and _call_succeeded(calls[_source_index(str(ref))])
        and _is_service_recovery_evidence(available[str(ref)])
    ]


def _source_index(source_id: str) -> int:
    try:
        return int(source_id.removeprefix("tool-")) - 1
    except ValueError:
        return -1


def _call_succeeded(call: Any) -> bool:
    if not isinstance(call, dict):
        return False
    if call.get("ok") is False:
        return False
    result = call.get("result")
    return not (isinstance(result, dict) and result.get("ok") is False)


def _is_live_mutation(call: Any) -> bool:
    if not isinstance(call, dict) or not _call_succeeded(call):
        return False
    name = str(call.get("tool_name") or "").lower()
    arguments = call.get("arguments") or {}
    encoded = f"{name} {arguments}".lower()
    if "run_ansible" in name:
        return arguments.get("check") is False
    if "kubectl" in name:
        return any(
            verb in name
            or f"'{verb}'" in encoded
            or f'"{verb}"' in encoded
            for verb in (
                "apply",
                "create",
                "delete",
                "patch",
                "replace",
                "scale",
                "set",
                "rollout",
                "cordon",
                "uncordon",
                "drain",
                "taint",
            )
        )
    return any(
        token in name
        for token in (
            "remediate",
            "mutation",
            "restart",
            "cordon",
            "uncordon",
            "drain",
            "scale",
            "patch",
        )
    ) and "write_file" not in name


def _is_service_recovery_evidence(evidence: dict[str, Any]) -> bool:
    tool_name = str(evidence.get("tool_name") or "").lower()
    if any(token in tool_name for token in ("kubectl", "ansible", "write_file")):
        return False
    encoded = f"{tool_name} {evidence.get('arguments') or ''}".lower()
    return any(
        token in encoded
        for token in (
            "prometheus",
            "query_range",
            "jaeger",
            "trace",
            "health",
            "curl",
            "wget",
            "grpcurl",
            "network.probe",
            "network_probe",
            "tcp_probe",
            "response_time",
            "latency",
            "error_rate",
            "traffic_rps",
        )
    )


def _successful_fix(
    labels: dict[str, Any],
    job: dict[str, Any],
    attempt_class: str | None,
    impact_class: str,
    recovery_proven: bool,
) -> bool:
    return (
        job.get("status") == "succeeded"
        and attempt_class == "targeted"
        and labels.get("addressed_injection") == "yes"
        and labels.get("target_correctness") == "correct"
        and labels.get("verification") == "correct"
        and impact_class == "helped"
        and recovery_proven
    )
