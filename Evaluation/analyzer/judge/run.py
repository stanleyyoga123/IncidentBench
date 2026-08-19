from pathlib import Path
from typing import Any

from analyzer.log import progress
from analyzer.sessions import compact_result, load_sessions, scenario_context, tool_call_summaries

from .client import JudgeClient
from .prompts import holistic_messages, rca_messages, remediation_messages
from .schemas import HOLISTIC_LABEL_SCHEMA, RCA_LABEL_SCHEMA, REMEDIATION_LABEL_SCHEMA
from .scorer import (
    END_WEIGHTS,
    annotate_run_outcomes,
    count_penalized_tools,
    end_score,
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
) -> dict[str, Any]:
    sessions = load_sessions(run_folder)
    context = scenario_context(metadata)
    raw = _collect_labels(sessions, context, client)
    return score_labeled_run(run_folder, metadata, errors, impact, raw, sessions, context)


def score_labeled_run(
    run_folder: Path,
    metadata: dict,
    errors: dict,
    impact: dict,
    raw: dict[str, Any],
    sessions: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sessions = sessions or load_sessions(run_folder)
    context = context or scenario_context(metadata)
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
    rem_results = [
        score_remediation_job(
            _labels_for_job(raw.get("remediation") or [], job, index),
            job,
            count_penalized_tools(job),
            ground_truth,
        )
        for index, job in enumerate(rem_jobs)
    ]
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
    highlights, categories = annotate_run_outcomes(rca_results, rem_results)
    holistic = dict(raw.get("holistic") or {})
    if any_match:
        holistic["rca_matched_injection"] = "yes"
    if any(item.get("impact_class") == "helped" and item.get("addressed_injection") == "yes" for item in rem_results):
        holistic["successfully_remediated"] = "yes"
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
            "rca": rca_score,
            "remediation": rem_slot,
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


def _collect_labels(sessions: dict, context: dict, client: JudgeClient) -> dict[str, Any]:
    raw: dict[str, Any] = {"rca": [], "remediation": [], "holistic": None}
    rca_jobs = sessions["rca"]
    rem_jobs = sessions["remediation"] or []
    progress(f"judge: {len(rca_jobs)} RCA session(s), {len(rem_jobs)} remediation job(s)")
    for index, job in enumerate(rca_jobs, start=1):
        progress(f"judge RCA {index}/{len(rca_jobs)}: {job.get('id')}")
        labels = client.complete(
            "rca_labels", RCA_LABEL_SCHEMA, rca_messages(_rca_payload(context, job, sessions))
        )
        raw["rca"].append(labels)
    for index, job in enumerate(rem_jobs, start=1):
        progress(f"judge remediation {index}/{len(rem_jobs)}: {job.get('id')}")
        labels = client.complete(
            "remediation_labels",
            REMEDIATION_LABEL_SCHEMA,
            remediation_messages(_remediation_payload(context, job, sessions)),
        )
        raw["remediation"].append(labels)
    progress("judge: holistic scenario classification")
    raw["holistic"] = client.complete(
        "holistic_labels",
        HOLISTIC_LABEL_SCHEMA,
        holistic_messages(
            {
                "ground_truth": context.get("ground_truth"),
                "scenario": context,
                "session_count": {"rca": len(rca_jobs), "remediation": len(rem_jobs)},
            }
        ),
    )
    return raw


def _labels_for_job(labels_list: list[dict[str, Any]], job: dict[str, Any], index: int) -> dict[str, Any]:
    job_id = str(job.get("id") or "")
    for item in labels_list:
        if str(item.get("session_id") or "") == job_id:
            return item
    if index < len(labels_list):
        return labels_list[index]
    return {"session_id": job_id}


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
        "anomalies": compact_result(sessions.get("anomaly") or []),
        "result": compact_result(job.get("result")),
        "tool_calls": tool_call_summaries(job.get("tool_calls") or []),
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
        "rca_result": compact_result((rca or {}).get("result")),
        "result": compact_result(job.get("result")),
        "tool_calls": tool_call_summaries(job.get("tool_calls") or []),
        "error": job.get("error"),
    }


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
