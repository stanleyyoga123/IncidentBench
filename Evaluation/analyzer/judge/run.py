import hashlib
import json
from pathlib import Path
from typing import Any

from analyzer.log import progress
from analyzer.sessions import (
    compact_result,
    load_sessions,
    scenario_context,
    tool_call_evidence,
    tool_call_summaries,
)

from .client import JudgeClient
from .prompts import holistic_messages, rca_messages, remediation_messages
from .schemas import HOLISTIC_LABEL_SCHEMA, RCA_LABEL_SCHEMA, REMEDIATION_LABEL_SCHEMA
from .scorer import (
    END_WEIGHTS,
    accuracy_metrics,
    annotate_run_outcomes,
    count_penalized_tools,
    end_score,
    efficiency_metrics,
    ground_truth_metrics,
    mean_or_none,
    operational_failure_count,
    operational_health,
    rca_component_score,
    remediator_component_score,
    score_rca_job,
    score_remediation_job,
)


def judge_run(
    run_folder: Path,
    metadata: dict,
    errors: dict,
    impact: dict,
    client: JudgeClient,
    checkpoint: Path | None = None,
    reference_answer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sessions = load_sessions(run_folder)
    context = scenario_context(metadata)
    context["reference_answer"] = reference_answer or {}
    context["ground_truth"]["reference_answer"] = reference_answer or {}
    raw = _collect_labels(
        sessions, context, client, checkpoint, errors=errors, impact=impact
    )
    return score_labeled_run(run_folder, metadata, errors, impact, raw, sessions, context)


def score_labeled_run(
    run_folder: Path,
    metadata: dict,
    errors: dict,
    impact: dict,
    raw: dict[str, Any],
    sessions: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    reference_answer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sessions = sessions or load_sessions(run_folder)
    context = context or scenario_context(metadata)
    if reference_answer is not None:
        context["reference_answer"] = reference_answer
        context["ground_truth"]["reference_answer"] = reference_answer
    ground_truth = context.get("ground_truth")
    rca_jobs = sessions["rca"]
    rem_jobs = sessions["remediation"] or []
    rca_results = [
        score_rca_job(
            _labels_for_job(raw.get("rca") or [], job, index),
            job,
            count_penalized_tools(job),
            ground_truth,
        )
        for index, job in enumerate(rca_jobs)
    ]
    rca_by_id = {str(item.get("session_id") or ""): item for item in rca_results}
    rem_results = [
        score_remediation_job(
            _labels_for_job(raw.get("remediation") or [], job, index),
            job,
            count_penalized_tools(job),
            ground_truth,
            rca_by_id.get(str(job.get("rca_job_id") or "")),
        )
        for index, job in enumerate(rem_jobs)
    ]
    successful_rca_ids = {
        item.get("rca_session_id")
        for item in rem_results
        if item.get("fix_outcome") == "success"
    }
    for item in rca_results:
        item["led_to_success"] = item.get("session_id") in successful_rca_ids
    invoked = bool(rem_jobs)
    correctly_skipped = (not invoked) and _correctly_skipped(sessions)
    rca_score = rca_component_score(rca_results)
    rem_slot = remediator_component_score(
        rem_results, rca_results, invoked, correctly_skipped
    )
    ops = operational_health(operational_failure_count(errors))
    observed = bool(impact.get("observed"))
    kinds = _session_kind_summary(rca_results)
    any_match = any(item.get("matched_injection") == "yes" for item in rca_results)
    rca_session_accuracy = mean_or_none(
        [float(item.get("score") or 0.0) for item in rca_results]
    ) or 0.0
    rca_injection_quality = max(
        (
            float(item.get("score") or 0.0)
            * {"yes": 1.0, "partial": 0.5, "no": 0.0}.get(
                str(item.get("matched_injection") or "no"), 0.0
            )
            for item in rca_results
        ),
        default=0.0,
    )
    highlights, categories = annotate_run_outcomes(rca_results, rem_results)
    holistic = dict(raw.get("holistic") or {})
    if any_match:
        holistic["rca_matched_injection"] = "yes"
    verified_remediations = [
        item for item in rem_results if _verified_remediation(item)
    ]
    recovery_accuracy = accuracy_metrics(rem_results)
    reference_metrics = ground_truth_metrics(rca_results, rem_results)
    efficiency = efficiency_metrics(rca_results, rem_results)
    scored_sessions = [*rca_results, *rem_results]
    evidence_coverage = (
        sum(bool(item.get("evidence_refs")) for item in scored_sessions)
        / len(scored_sessions)
        if scored_sessions
        else 0.0
    )
    judge_confidence = mean_or_none(
        [
            {"high": 1.0, "medium": 0.5, "low": 0.0}.get(
                str(item.get("confidence") or "low"), 0.0
            )
            for item in scored_sessions
        ]
    ) or 0.0
    judge_error_count = sum(
        bool(item.get("judge_error")) for item in scored_sessions
    )
    holistic["successfully_remediated"] = _remediation_outcome(
        rem_results, invoked, verified_remediations
    )
    final = end_score(
        impact_observed=observed,
        rca_score=rca_score,
        remediator_score=rem_slot,
        operational=ops,
    )
    return {
        "skipped": False,
        "rca": rca_results,
        "remediation": rem_results,
        "holistic": holistic,
        "highlights": highlights,
        "categories": categories,
        "weights": END_WEIGHTS,
        "components": {
            "impact_observed": observed,
            "evaluation_valid": observed,
            "rca": rca_score,
            "rca_session_accuracy": rca_session_accuracy,
            "rca_injection_quality": rca_injection_quality,
            "remediation": rem_slot,
            "verified_remediation_count": len(verified_remediations),
            "remediation_recovery_accuracy": recovery_accuracy["accuracy"],
            "remediation_recovery_accuracy_complete": recovery_accuracy[
                "accuracy_complete"
            ],
            **reference_metrics,
            **efficiency,
            "evidence_coverage": evidence_coverage,
            "judge_confidence": judge_confidence,
            "metric_confidence": evidence_coverage * judge_confidence,
            "judge_error_count": judge_error_count,
            "holistic_judge_error": bool(holistic.get("_judge_error")),
            "operational": ops,
            "remediator_invoked": invoked,
            "correctly_skipped_remediation": correctly_skipped,
            "true_positive_count": kinds["true_positive_count"],
            "false_alarm_count": kinds["false_alarm_count"],
            "true_positive_rca": kinds["true_positive_score"],
            "false_alarm_rca": kinds["false_alarm_score"],
            "rca_matched_injection": any_match,
            "helped_count": len(categories["helped"]),
            "harmed_count": len(categories["harmed"]),
            "no_impact_count": len(categories["no_impact"]),
            "best_session": (highlights.get("best") or {}).get("session_id"),
            "worst_session": (highlights.get("worst") or {}).get("session_id"),
        },
        "end_score": final,
        "raw": {
            "rca": list(raw.get("rca") or []),
            "remediation": list(raw.get("remediation") or []),
            "holistic": raw.get("holistic"),
        },
    }


def _collect_labels(
    sessions: dict,
    context: dict,
    client: JudgeClient,
    checkpoint: Path | None = None,
    *,
    errors: dict[str, Any] | None = None,
    impact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rca_jobs = sessions["rca"]
    rem_jobs = sessions["remediation"] or []
    raw = _load_checkpoint(checkpoint)
    progress(f"judge: {len(rca_jobs)} RCA session(s), {len(rem_jobs)} remediation job(s)")
    for index, job in enumerate(rca_jobs, start=1):
        payload = _rca_payload(context, job, sessions)
        input_hash = _input_hash("rca-v4", payload, client)
        existing = _existing_label(raw["rca"], job, input_hash)
        if existing is not None:
            progress(f"judge RCA {index}/{len(rca_jobs)}: {job.get('id')} (cached)")
            continue
        progress(f"judge RCA {index}/{len(rca_jobs)}: {job.get('id')}")
        labels = _complete_or_fallback(
            client,
            "rca_labels",
            RCA_LABEL_SCHEMA,
            rca_messages(payload),
            _rca_failure_label(job),
        )
        labels["session_id"] = str(job.get("id") or "")
        labels["_input_hash"] = input_hash
        raw["rca"] = _replace_label(raw["rca"], labels)
        _save_checkpoint(checkpoint, raw)
    for index, job in enumerate(rem_jobs, start=1):
        payload = _remediation_payload(context, job, sessions)
        input_hash = _input_hash("remediation-v4", payload, client)
        existing = _existing_label(raw["remediation"], job, input_hash)
        if existing is not None:
            progress(f"judge remediation {index}/{len(rem_jobs)}: {job.get('id')} (cached)")
            continue
        progress(f"judge remediation {index}/{len(rem_jobs)}: {job.get('id')}")
        labels = _complete_or_fallback(
            client,
            "remediation_labels",
            REMEDIATION_LABEL_SCHEMA,
            remediation_messages(payload),
            _remediation_failure_label(job),
        )
        labels["session_id"] = str(job.get("id") or "")
        labels["_input_hash"] = input_hash
        raw["remediation"] = _replace_label(raw["remediation"], labels)
        _save_checkpoint(checkpoint, raw)
    holistic_payload = _holistic_payload(
        context, sessions, errors or {}, impact or {}
    )
    holistic_hash = _input_hash("holistic-v4", holistic_payload, client)
    if (
        raw.get("holistic")
        and raw["holistic"].get("_input_hash") == holistic_hash
        and not raw["holistic"].get("_judge_error")
    ):
        progress("judge: holistic scenario classification (cached)")
    else:
        progress("judge: holistic scenario classification")
        raw["holistic"] = _complete_or_fallback(
            client,
            "holistic_labels",
            HOLISTIC_LABEL_SCHEMA,
            holistic_messages(holistic_payload),
            _holistic_failure_label(sessions, impact or {}),
        )
        raw["holistic"]["_input_hash"] = holistic_hash
        _save_checkpoint(checkpoint, raw)
    return raw


def _load_checkpoint(checkpoint: Path | None) -> dict[str, Any]:
    empty = {"rca": [], "remediation": [], "holistic": None}
    if checkpoint is None or not checkpoint.is_file():
        return empty
    try:
        payload = json.loads(checkpoint.read_text())
    except (OSError, json.JSONDecodeError):
        return empty
    if not isinstance(payload, dict):
        return empty
    return {
        "rca": list(payload.get("rca") or []),
        "remediation": list(payload.get("remediation") or []),
        "holistic": payload.get("holistic"),
    }


def _save_checkpoint(checkpoint: Path | None, raw: dict[str, Any]) -> None:
    if checkpoint is None:
        return
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(json.dumps(raw, indent=2, default=str))


def _complete_or_fallback(
    client: JudgeClient,
    name: str,
    schema: dict[str, Any],
    messages: list[dict[str, str]],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    """Keep a run analyzable when one judge request is unavailable.

    The fallback is intentionally zero-credit and marked retryable. A later normal
    run will ignore its cache entry and ask the judge again.
    """
    try:
        return client.complete(name, schema, messages)
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"[:500]
        progress(f"judge request failed for {name}; using retryable fallback ({detail})")
        result = dict(fallback)
        result["_judge_error"] = detail
        return result


def _rca_failure_label(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": str(job.get("id") or ""),
        "session_kind": "false_alarm",
        "attempt_class": "false_alarm",
        "matched_injection": "no",
        "localization": "incorrect",
        "evidence_quality": "incorrect",
        "necessity": "incorrect",
        "plan_quality": "incorrect",
        "grounding": "incorrect",
        "false_alarm_recognition": "incorrect",
        "harmlessness": "incorrect",
        "impact_class": "no_impact",
        "evidence": "Judge unavailable; no credit assigned.",
        "evidence_refs": [],
        "confidence": "low",
    }


def _remediation_failure_label(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": str(job.get("id") or ""),
        "addressed_injection": "no",
        "attempt_class": "false_alarm",
        "plan_alignment": "incorrect",
        "target_correctness": "incorrect",
        "execution_discipline": "incorrect",
        "verification": "incorrect",
        "safety": "incorrect",
        "recovery_proven": "unclear",
        "recovery_evidence_refs": [],
        "impact_class": "no_impact",
        "evidence": "Judge unavailable; no credit assigned.",
        "evidence_refs": [],
        "confidence": "low",
    }


def _holistic_failure_label(
    sessions: dict[str, Any], impact: dict[str, Any]
) -> dict[str, Any]:
    attempted = bool(sessions.get("remediation") or [])
    return {
        "impact_observed": "yes" if impact.get("observed") else "unclear",
        "rca_matched_injection": "no",
        "remediation_attempted": "yes" if attempted else "no",
        "successfully_remediated": "no" if attempted else "not_attempted",
        "impact_narrative": "Holistic judge unavailable; no positive outcome inferred.",
    }


def _existing_label(
    labels_list: list[dict[str, Any]],
    job: dict[str, Any],
    input_hash: str,
) -> dict[str, Any] | None:
    job_id = str(job.get("id") or "")
    for item in reversed(labels_list):
        if (
            str(item.get("session_id") or "") == job_id
            and item.get("_input_hash") == input_hash
            and not item.get("_judge_error")
        ):
            return item
    return None


def _labels_for_job(labels_list: list[dict[str, Any]], job: dict[str, Any], index: int) -> dict[str, Any]:
    job_id = str(job.get("id") or "")
    for item in reversed(labels_list):
        if str(item.get("session_id") or "") == job_id:
            return item
    if index < len(labels_list):
        return labels_list[index]
    return {"session_id": job_id}


def _replace_label(
    labels_list: list[dict[str, Any]], labels: dict[str, Any]
) -> list[dict[str, Any]]:
    session_id = str(labels.get("session_id") or "")
    return [
        item
        for item in labels_list
        if str(item.get("session_id") or "") != session_id
    ] + [labels]


def _session_kind_summary(rca_results: list[dict[str, Any]]) -> dict[str, Any]:
    true_positive = [
        item["score"] for item in rca_results if item.get("session_kind") == "true_positive"
    ]
    false_alarm = [
        item["score"] for item in rca_results if item.get("session_kind") == "false_alarm"
    ]
    return {
        "true_positive_count": len(true_positive),
        "false_alarm_count": len(false_alarm),
        "true_positive_score": mean_or_none(true_positive),
        "false_alarm_score": mean_or_none(false_alarm),
    }


def _correctly_skipped(sessions: dict) -> bool:
    workflows = sessions["workflow"]
    if any(item.get("status") == "completed_no_action" for item in workflows):
        return True
    required = [
        (item.get("result") or {}).get("remediation_required") is True
        for item in sessions["rca"]
    ]
    return bool(required) and not any(required)


def _rca_payload(context, job, sessions) -> dict:
    return {
        "session_id": str(job.get("id")),
        "status": job.get("status"),
        "ground_truth": context.get("ground_truth"),
        "scenario": context,
        "anomalies": compact_result(sessions.get("anomaly") or [], 2500),
        "result": compact_result(job.get("result"), 5000),
        "tool_calls": tool_call_summaries(job.get("tool_calls") or []),
        "tool_evidence": tool_call_evidence(job.get("tool_calls") or []),
        "error": job.get("error"),
        "workflow": _related_workflow(sessions, job.get("workflow_id")),
    }


def _remediation_payload(context, job, sessions) -> dict:
    rca = next(
        (item for item in sessions["rca"] if str(item.get("id")) == str(job.get("rca_job_id"))),
        None,
    )
    return {
        "session_id": str(job.get("id")),
        "status": job.get("status"),
        "ground_truth": context.get("ground_truth"),
        "scenario": context,
        "rca_result": compact_result((rca or {}).get("result"), 3500),
        "result": compact_result(job.get("result"), 5000),
        "tool_calls": tool_call_summaries(job.get("tool_calls") or []),
        "tool_evidence": tool_call_evidence(job.get("tool_calls") or []),
        "error": job.get("error"),
    }


def _holistic_payload(
    context: dict[str, Any],
    sessions: dict[str, Any],
    errors: dict[str, Any],
    impact: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ground_truth": context.get("ground_truth"),
        "scenario": context,
        "metric_impact": impact,
        "session_count": {
            "rca": len(sessions["rca"]),
            "remediation": len(sessions["remediation"] or []),
        },
        "rca_outcomes": compact_result(
            [_job_outcome(item) for item in sessions["rca"]], 6000
        ),
        "remediation_outcomes": compact_result(
            [_job_outcome(item) for item in sessions["remediation"] or []], 6000
        ),
        "workflow_outcomes": compact_result(
            [
                {
                    "id": item.get("id"),
                    "status": item.get("status"),
                    "decision": item.get("decision"),
                    "error": item.get("error"),
                }
                for item in sessions["workflow"]
            ],
            2500,
        ),
        "operational_errors": {
            "agent_error_count": errors.get("agent_error_count", 0),
            "failed_tool_count": errors.get("failed_tool_count", 0),
            "terminal_errors": [
                item
                for item in errors.get("errors") or []
                if item.get("kind") in {"job_status", "job_error", "workflow"}
            ],
        },
    }


def _job_outcome(job: dict[str, Any]) -> dict[str, Any]:
    result = job.get("result") or {}
    return {
        "id": job.get("id"),
        "status": job.get("status"),
        "summary": compact_result(result.get("summary"), 1800),
        "root_cause": compact_result(result.get("root_cause"), 1200),
        "incident_state": result.get("incident_state"),
        "remediation_required": result.get("remediation_required"),
        "changes": compact_result(result.get("changes") or [], 1800),
        "verification": compact_result(result.get("verification") or [], 1800),
        "error": job.get("error"),
    }


def _input_hash(kind: str, payload: dict[str, Any], client: JudgeClient) -> str:
    identity = {
        "kind": kind,
        "client": type(client).__name__,
        "model": getattr(client, "model", None),
        "payload": payload,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _verified_remediation(item: dict[str, Any]) -> bool:
    return item.get("fix_outcome") == "success"


def _remediation_outcome(
    rem_results: list[dict[str, Any]],
    invoked: bool,
    verified: list[dict[str, Any]],
) -> str:
    if verified:
        return "yes"
    if not invoked:
        return "not_attempted"
    if any(
        item.get("addressed_injection") in {"yes", "partial"}
        and (item.get("labels") or {}).get("verification") == "partial"
        and item.get("impact_class") != "harmed"
        for item in rem_results
    ):
        return "partial"
    return "no"


def _related_workflow(sessions, workflow_id) -> dict[str, Any] | None:
    if not workflow_id:
        return None
    for workflow in sessions["workflow"]:
        if str(workflow.get("id")) == str(workflow_id):
            return {
                "id": workflow.get("id"),
                "status": workflow.get("status"),
                "decision": workflow.get("decision"),
            }
    return None
