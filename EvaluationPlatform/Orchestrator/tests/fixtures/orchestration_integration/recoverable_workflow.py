from typing import Any
from uuid import UUID

from features.agent_workflow.schema import Workflow
from fixtures.orchestration_integration.split_services import SplitServices, workflow


class RecoverableWorkflow:
    """Controlled persistence boundary retaining committed workflow transitions."""

    def __init__(self, services: SplitServices, current: Workflow | None = None) -> None:
        self.current = current
        self.anomalies = [{"event_id": "a" * 64, "namespace": "shop", "name": "checkout"}]
        repository = services.repository
        repository.claim_pending.side_effect = self.claim_pending
        repository.list_reconcilable.side_effect = lambda: [self.current] if self.current else []
        repository.get_workflow.side_effect = lambda _id: self.current
        repository.anomaly_payloads.return_value = self.anomalies
        repository.retrieve_lessons.return_value = []
        repository.decide.side_effect = self.decide
        repository.attach_rca_job.side_effect = self.attach_rca_job
        repository.attach_remediation_job.side_effect = self.attach_remediation_job
        repository.reset_for_retry.side_effect = self.reset_for_retry

    def claim_pending(self, _limit: int) -> tuple[Workflow, list[dict[str, Any]]]:
        assert self.current is None
        self.current = workflow("rca_submitting")
        return self.current, self.anomalies

    def decide(self, _id: UUID, decision: str, actor: str, reason: str, expected_version: int) -> Workflow:
        assert self.current is not None
        assert self.current.status == "awaiting_approval"
        assert self.current.version == expected_version
        self.current = self.current.model_copy(update={
            "status": "remediation_submitting", "version": expected_version + 1,
            "decision": decision, "decision_actor": actor, "decision_reason": reason,
        })
        return self.current

    def attach_rca_job(self, _id: UUID, job_id: UUID) -> None:
        assert self.current is not None
        self.current = self.current.model_copy(update={
            "status": "rca_queued", "rca_job_id": job_id, "version": self.current.version + 1,
        })

    def attach_remediation_job(self, _id: UUID, job_id: UUID) -> None:
        assert self.current is not None
        self.current = self.current.model_copy(update={
            "status": "remediation_queued", "remediation_job_id": job_id,
            "version": self.current.version + 1,
        })

    def reset_for_retry(self, _id: UUID, expected_version: int, actor: str, reason: str) -> Workflow:
        assert self.current is not None
        assert self.current.status == "failed"
        assert self.current.version == expected_version
        self.current = self.current.model_copy(update={
            "status": "remediation_submitting" if self.current.remediation_job_id else "rca_submitting",
            "version": expected_version + 1, "decision_actor": actor, "decision_reason": reason,
            "error": None,
        })
        return self.current
