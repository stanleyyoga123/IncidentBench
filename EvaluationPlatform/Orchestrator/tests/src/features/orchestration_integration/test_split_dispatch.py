import hashlib
import json

import pytest

from fixtures.orchestration_integration.split_services import (
    RCA_ID, REMEDIATION_ID, WORKFLOW_ID, SplitServices, workflow,
)


def test_intake_claims_in_evaluation_and_submits_scoped_rca(split_services: SplitServices) -> None:
    """Dispatch ownership moved; the documented claim and RCA payload survive HTTP."""
    services = split_services
    anomalies = [{"event_id": "a" * 64, "namespace": "shop", "name": "checkout"}]
    lessons = [{"id": "lesson-1", "summary": "Verify the deployment's current state."}]
    services.repository.claim_pending.return_value = (workflow("rca_submitting"), anomalies)
    services.repository.retrieve_lessons.return_value = lessons
    services.agent_responses[("POST", "/api/v1/rca/jobs")] = {"id": str(RCA_ID), "status": "queued"}

    assert services.coordinator.intake_once() == 1

    services.repository.claim_pending.assert_called_once_with(100)
    services.repository.retrieve_lessons.assert_called_once_with(anomalies)
    services.repository.attach_rca_job.assert_called_once_with(WORKFLOW_ID, RCA_ID)
    submission = next(request for request in services.requests if request.url.host == "rca")
    assert json.loads(submission.content) == {
        "workflow_id": str(WORKFLOW_ID), "anomalies": anomalies, "historical_lessons": lessons,
    }
    assert submission.headers["Idempotency-Key"] == f"workflow:{WORKFLOW_ID}:rca:1"


def test_reconciliation_auto_approves_and_submits_matching_rca_snapshot(split_services: SplitServices) -> None:
    """The existing automated approval and snapshot contract crosses both services."""
    services = split_services
    pending = workflow("awaiting_approval", rca_job_id=RCA_ID)
    approved = pending.model_copy(update={
        "status": "remediation_submitting", "version": 2,
        "decision_actor": "agent-orchestrator",
        "decision_reason": "automatic approval after RCA required remediation",
    })
    services.repository.list_reconcilable.return_value = [pending]
    services.repository.decide.return_value = approved
    services.repository.get_workflow.return_value = approved
    result = {"remediation_required": True, "summary": "Deployment needs recovery."}
    services.agent_responses[("GET", f"/api/v1/rca/jobs/{RCA_ID}")] = {
        "id": str(RCA_ID), "status": "succeeded", "result": result,
    }
    services.agent_responses[("POST", "/api/v1/remediation/jobs")] = {
        "id": str(REMEDIATION_ID), "status": "queued",
    }

    assert services.coordinator.reconcile_once() == 1

    submission = next(request for request in services.requests if request.url.host == "remediator")
    payload = json.loads(submission.content)
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"))
    assert payload["rca_result"] == result
    assert payload["rca_result_sha256"] == hashlib.sha256(canonical.encode()).hexdigest()
    assert payload["approval"] == {
        "actor": "agent-orchestrator", "reason": "automatic approval after RCA required remediation",
        "workflow_version": 2,
    }
    services.repository.decide.assert_called_once_with(
        WORKFLOW_ID, "approved", "agent-orchestrator",
        "automatic approval after RCA required remediation", 1,
    )
    services.repository.attach_remediation_job.assert_called_once_with(WORKFLOW_ID, REMEDIATION_ID)


def test_maintenance_blocks_dispatch_and_remote_writes_but_exports_remain_available(split_services: SplitServices) -> None:
    """Runner maintenance must gate the separate dispatcher and all persistence writes."""
    services = split_services
    headers = {"Authorization": "Bearer control"}
    run = {"run_id": "split-integration"}
    assert services.evaluation.post("/api/v1/evaluation/acquire", headers=headers, json=run).status_code == 200

    with pytest.raises(services.conflict_error, match="maintenance"):
        services.coordinator.intake_once()
    assert services.requests == []
    with pytest.raises(services.conflict_error, match="maintenance"):
        services.store_client.claim_pending(100)
    services.repository.claim_pending.assert_not_called()
    path = "/api/v1/internal/orchestration/workflows/claim"
    assert services.evaluation.post(path, headers=headers, json={"limit": 100}).status_code == 401
    exported = services.evaluation.get("/api/v1/evaluation/export", headers=headers, params=run)
    assert exported.status_code == 200, exported.text
    assert set(exported.json()["sessions"]) == {
        "anomaly", "rca_session", "remediation_run", "remediation_session", "learning_session", "workflow",
    }
