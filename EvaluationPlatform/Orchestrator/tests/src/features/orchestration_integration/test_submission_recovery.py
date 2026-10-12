from uuid import UUID

import httpx
import pytest

from features.agent_workflow.schema import RetryRequest
from fixtures.orchestration_integration.recoverable_workflow import RecoverableWorkflow
from fixtures.orchestration_integration.split_services import (
    RCA_ID, REMEDIATION_ID, WORKFLOW_ID, SplitServices, workflow,
)


@pytest.mark.parametrize("stage", ["claim", "decision", "rca_attachment", "remediation_attachment"])
def test_reconcile_recovers_committed_submission_when_persistence_response_is_lost(
    split_services: SplitServices, stage: str,
) -> None:
    """A lost HTTP acknowledgement must preserve the durable incident and its job."""
    services = split_services
    remediation = stage in {"decision", "remediation_attachment"}
    state = RecoverableWorkflow(
        services, workflow("awaiting_approval", rca_job_id=RCA_ID) if remediation else None,
    )
    paths = {
        "claim": "/api/v1/internal/orchestration/workflows/claim",
        "decision": f"/api/v1/internal/orchestration/workflows/{WORKFLOW_ID}/decision",
        "rca_attachment": f"/api/v1/internal/orchestration/workflows/{WORKFLOW_ID}/rca/attach",
        "remediation_attachment": f"/api/v1/internal/orchestration/workflows/{WORKFLOW_ID}/remediation/attach",
    }
    services.lose_responses.add(paths[stage])
    services.agent_responses.update({
        ("POST", "/api/v1/rca/jobs"): {"id": str(RCA_ID), "status": "queued"},
        ("GET", f"/api/v1/rca/jobs/{RCA_ID}"): {
            "id": str(RCA_ID), "status": "succeeded" if remediation else "queued",
            "result": {"remediation_required": True, "summary": "Recover checkout."},
        },
        ("POST", "/api/v1/remediation/jobs"): {"id": str(REMEDIATION_ID), "status": "queued"},
        ("GET", f"/api/v1/remediation/jobs/{REMEDIATION_ID}"): {
            "id": str(REMEDIATION_ID), "status": "queued",
        },
    })

    if remediation:
        services.coordinator.reconcile_once()
    else:
        with pytest.raises(services.persistence_error):
            services.coordinator.intake_once()
    assert not services.lose_responses

    services.coordinator.reconcile_once()

    assert state.current is not None
    assert state.current.status == ("remediation_queued" if remediation else "rca_queued")
    assert (state.current.remediation_job_id if remediation else state.current.rca_job_id) == (
        REMEDIATION_ID if remediation else RCA_ID
    )
    expected_service = "remediator" if remediation else "rca"
    expected_job = "remediation" if remediation else "rca"
    assert list(services.downstream_jobs) == [
        (expected_service, f"workflow:{WORKFLOW_ID}:{expected_job}:1"),
    ]
    services.repository.fail_submission.assert_not_called()
    services.repository.mark_submission_failed.assert_not_called()
    services.repository.reset_for_retry.assert_not_called()


@pytest.mark.parametrize("service,job_id", [("rca", RCA_ID), ("remediation", REMEDIATION_ID)])
def test_reconcile_reuses_downstream_job_when_created_job_response_is_lost(
    split_services: SplitServices, service: str, job_id: UUID,
) -> None:
    """Ambiguous creation retries the same idempotent submission, never a new job."""
    services = split_services
    remediation = service == "remediation"
    state = RecoverableWorkflow(
        services, workflow("awaiting_approval", rca_job_id=RCA_ID) if remediation else None,
    )
    path = f"/api/v1/{service}/jobs"
    services.lose_responses.add(path)
    services.agent_responses[("POST", path)] = {"id": str(job_id), "status": "queued"}
    services.agent_responses[("GET", f"/api/v1/rca/jobs/{RCA_ID}")] = {
        "id": str(RCA_ID), "status": "succeeded",
        "result": {"remediation_required": True, "summary": "Recover checkout."},
    }

    if remediation:
        services.coordinator.reconcile_once()
    else:
        with pytest.raises(httpx.ReadTimeout):
            services.coordinator.intake_once()
    services.coordinator.reconcile_once()

    submissions = [request for request in services.requests if request.url.path == path]
    assert len(submissions) == 2
    assert submissions[0].headers["Idempotency-Key"] == submissions[1].headers["Idempotency-Key"]
    assert submissions[0].content == submissions[1].content
    assert len(services.downstream_jobs) == 1
    assert state.current is not None
    assert state.current.status == f"{service}_queued"
    assert (state.current.remediation_job_id if remediation else state.current.rca_job_id) == job_id
    services.repository.fail_submission.assert_not_called()
    services.repository.mark_submission_failed.assert_not_called()
    services.repository.reset_for_retry.assert_not_called()


def test_reconcile_preserves_explicit_retry_attempt_after_lost_reset_response(
    split_services: SplitServices,
) -> None:
    """Recover a committed retry using its new attempt, preserving the prior job."""
    services = split_services
    prior_job = UUID("00000000-0000-0000-0000-000000000004")
    failed = workflow("failed", rca_job_id=prior_job).model_copy(update={"version": 4})
    state = RecoverableWorkflow(services, failed)
    services.lose_responses.add(f"/api/v1/internal/orchestration/workflows/{WORKFLOW_ID}/retry")
    services.agent_responses[("POST", "/api/v1/rca/jobs")] = {"id": str(RCA_ID), "status": "queued"}
    request = RetryRequest(actor="operator", reason="Retry the failed analysis", expected_version=4)

    with pytest.raises(services.persistence_error):
        services.coordinator.retry(WORKFLOW_ID, request)
    services.coordinator.reconcile_once()

    assert state.current is not None
    assert state.current.status == "rca_queued"
    assert state.current.rca_job_id == RCA_ID
    assert list(services.downstream_jobs) == [("rca", f"workflow:{WORKFLOW_ID}:rca:5")]
    services.repository.reset_for_retry.assert_called_once_with(WORKFLOW_ID, 4, request.actor, request.reason)
    services.repository.mark_submission_failed.assert_not_called()
