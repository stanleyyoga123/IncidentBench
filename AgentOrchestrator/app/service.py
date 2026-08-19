import logging
import threading
from typing import Any
from uuid import UUID

import httpx

from clients import AgentClient
from schema import Workflow
from store import WorkflowConflictError, WorkflowStore


LOGGER = logging.getLogger("AgentOrchestrator")
AUTO_APPROVAL_ACTOR = "agent-orchestrator"
AUTO_APPROVAL_REASON = "automatic approval after RCA required remediation"


class WorkflowCoordinator:
    def __init__(
        self,
        store: WorkflowStore,
        rca: AgentClient,
        remediator: AgentClient,
        *,
        batch_size: int,
    ):
        self.store = store
        self.rca = rca
        self.remediator = remediator
        self.batch_size = batch_size

    def intake_once(self) -> int:
        if not self.store.execution_available():
            return 0
        claimed = self.store.claim_pending(self.batch_size)
        if claimed is None:
            return 0
        workflow, anomalies = claimed
        try:
            job = self.rca.create_rca(workflow.id, anomalies)
            self.store.attach_rca_job(workflow.id, job.id)
            return len(anomalies)
        except Exception as exc:
            self.store.fail_submission(workflow.id, self._error(exc))
            LOGGER.exception("Failed to submit RCA workflow %s", workflow.id)
            return 0

    def submit_approved_remediation(
        self,
        workflow_id: UUID,
        actor: str,
        reason: str,
        expected_version: int,
    ) -> Workflow:
        workflow = self.store.decide(
            workflow_id, "approved", actor, reason, expected_version
        )
        try:
            rca_job = self.rca.get_rca(workflow.rca_job_id)
            job = self.remediator.create_remediation(
                workflow.id,
                rca_job,
                {
                    "actor": actor,
                    "reason": reason,
                    "workflow_version": workflow.version,
                },
            )
            self.store.attach_remediation_job(workflow.id, job.id)
            return self.store.get_workflow(workflow.id)
        except Exception as exc:
            self.store.mark_submission_failed(workflow.id, self._error(exc))
            raise

    def reconcile_once(self) -> int:
        updated = 0
        for workflow in self.store.list_reconcilable():
            try:
                if workflow.status == "awaiting_approval":
                    self.submit_approved_remediation(
                        workflow.id,
                        AUTO_APPROVAL_ACTOR,
                        AUTO_APPROVAL_REASON,
                        workflow.version,
                    )
                    updated += 1
                elif workflow.status.startswith("rca_") and workflow.rca_job_id:
                    job = self.rca.get_rca(workflow.rca_job_id)
                    expected = "rca_running" if job.status == "running" else "rca_queued"
                    if job.status in {"queued", "running"} and workflow.status == expected:
                        continue
                    self.store.set_rca_state(
                        workflow.id,
                        job.status,
                        result=job.result,
                        error=job.error,
                    )
                    updated += 1
                    if (
                        job.status == "succeeded"
                        and (job.result or {}).get("remediation_required") is True
                    ):
                        current = self.store.get_workflow(workflow.id)
                        if current is not None:
                            self.submit_approved_remediation(
                                current.id,
                                AUTO_APPROVAL_ACTOR,
                                AUTO_APPROVAL_REASON,
                                current.version,
                            )
                elif workflow.status.startswith("remediation_") and workflow.remediation_job_id:
                    job = self.remediator.get_remediation(workflow.remediation_job_id)
                    expected = "remediation_running" if job.status == "running" else "remediation_queued"
                    if job.status in {"queued", "running"} and workflow.status == expected:
                        continue
                    self.store.set_remediation_state(
                        workflow.id,
                        job.status,
                        error=job.error,
                    )
                    updated += 1
            except (httpx.HTTPError, ValueError, WorkflowConflictError):
                LOGGER.exception("Failed to reconcile workflow %s", workflow.id)
        return updated

    @staticmethod
    def _error(exc: Exception) -> dict[str, Any]:
        return {"type": type(exc).__name__, "message": str(exc)}


class CoordinatorLoops:
    def __init__(
        self,
        coordinator: WorkflowCoordinator,
        intake_interval: float,
        reconcile_interval: float,
    ):
        self.coordinator = coordinator
        self.intake_interval = intake_interval
        self.reconcile_interval = reconcile_interval
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []

    def start(self) -> None:
        self.threads = [
            threading.Thread(target=self._intake_loop, daemon=True),
            threading.Thread(target=self._reconcile_loop, daemon=True),
        ]
        for thread in self.threads:
            thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=10)

    def _intake_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.coordinator.intake_once()
            except Exception:
                LOGGER.exception("Intake iteration failed")
            self.stop_event.wait(self.intake_interval)

    def _reconcile_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.coordinator.reconcile_once()
            except Exception:
                LOGGER.exception("Reconcile iteration failed")
            self.stop_event.wait(self.reconcile_interval)
