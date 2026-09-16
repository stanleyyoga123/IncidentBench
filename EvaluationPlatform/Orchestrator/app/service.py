from contextlib import nullcontext
from functools import wraps
import logging
import json
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


def running_only(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        guard = getattr(self.store, "running_guard", nullcontext)
        with guard():
            return method(self, *args, **kwargs)
    return guarded


class WorkflowCoordinator:
    def __init__(
        self,
        store: WorkflowStore,
        rca: AgentClient,
        remediator: AgentClient,
        learning: AgentClient,
        *,
        batch_size: int,
    ):
        self.store = store
        self.rca = rca
        self.remediator = remediator
        self.learning = learning
        self.batch_size = batch_size

    @running_only
    def intake_once(self) -> int:
        if not self.store.execution_available():
            return 0
        claimed = self.store.claim_pending(self.batch_size)
        if claimed is None:
            return 0
        workflow, anomalies = claimed
        try:
            lessons = self.store.retrieve_lessons(anomalies)
            job = self.rca.create_rca(
                workflow.id, anomalies, historical_lessons=lessons
            )
            self.store.attach_rca_job(workflow.id, job.id)
            return len(anomalies)
        except Exception as exc:
            self.store.fail_submission(workflow.id, self._error(exc))
            LOGGER.exception("Failed to submit RCA workflow %s", workflow.id)
            return 0

    @running_only
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

    @running_only
    def submit_learning(self, workflow: Workflow) -> Workflow:
        rca_job = self.rca.get_rca(workflow.rca_job_id)
        remediation_job = (
            self.remediator.get_remediation(workflow.remediation_job_id)
            if workflow.remediation_job_id
            else None
        )
        source = self._json_safe(
            {
                "workflow_id": str(workflow.id),
                "completion_type": (
                    "remediated" if remediation_job is not None else "no_action"
                ),
                "anomalies": self.store.anomaly_payloads(workflow.id),
                "rca": {
                    "job_id": str(rca_job.id),
                    "result": rca_job.result,
                },
                "remediation": (
                    {"job_id": str(remediation_job.id), "result": remediation_job.result}
                    if remediation_job is not None
                    else None
                ),
                "tool_calls": self._bounded_tool_calls(
                    self.store.tool_calls_for_workflow(workflow)
                ),
            }
        )
        job = self.learning.create_learning(workflow.id, source)
        self.store.attach_learning_job(workflow.id, job.id)
        return self.store.get_workflow(workflow.id)

    @running_only
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
                    elif job.status == "succeeded":
                        current = self.store.get_workflow(workflow.id)
                        if current is not None:
                            self.submit_learning(current)
                elif (workflow.status.startswith("remediation_") or workflow.status == "needs_review") and workflow.remediation_job_id:
                    job = self.remediator.get_remediation(workflow.remediation_job_id)
                    if job.status == "needs_review":
                        # Finish legacy review records automatically during rolling upgrades.
                        self.store.finish_remediation_job(job.id, "failed", error=job.error)
                    expected = "remediation_running" if job.status == "running" else "remediation_queued"
                    if job.status in {"queued", "running"} and workflow.status == expected:
                        continue
                    self.store.set_remediation_state(
                        workflow.id,
                        job.status,
                        error=job.error,
                    )
                    updated += 1
                    if job.status == "succeeded":
                        current = self.store.get_workflow(workflow.id)
                        if current is not None:
                            self.submit_learning(current)
                elif workflow.status == "learning_submitting":
                    self.submit_learning(workflow)
                    updated += 1
                elif workflow.status.startswith("learning_") and workflow.learning_job_id:
                    job = self.learning.get_learning(workflow.learning_job_id)
                    expected = (
                        "learning_running" if job.status == "running" else "learning_queued"
                    )
                    if job.status in {"queued", "running"} and workflow.status == expected:
                        continue
                    self.store.set_learning_state(
                        workflow.id, job.status, error=job.error
                    )
                    updated += 1
            except (httpx.HTTPError, ValueError, WorkflowConflictError):
                LOGGER.exception("Failed to reconcile workflow %s", workflow.id)
        return updated

    @staticmethod
    def _error(exc: Exception) -> dict[str, Any]:
        return {"type": type(exc).__name__, "message": str(exc)}

    @staticmethod
    def _json_safe(value: Any) -> Any:
        return json.loads(json.dumps(value, default=str))

    @classmethod
    def _bounded_tool_calls(cls, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        bounded = []
        for call in calls[:100]:
            item = cls._json_safe(call)
            encoded = json.dumps(item, sort_keys=True, separators=(",", ":"))
            if len(encoded) > 4_000:
                item = {
                    "id": item.get("id"),
                    "service": item.get("service"),
                    "job_id": item.get("job_id"),
                    "tool_name": item.get("tool_name"),
                    "ok": item.get("ok"),
                    "created_at": item.get("created_at"),
                    "arguments_excerpt": json.dumps(
                        item.get("arguments"), default=str
                    )[:1_000],
                    "result_excerpt": json.dumps(
                        item.get("result"), default=str
                    )[:2_000],
                    "truncated": True,
                }
            bounded.append(item)
        return bounded


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
            except WorkflowConflictError:
                LOGGER.debug("Intake paused by evaluation maintenance")
            except Exception:
                LOGGER.exception("Intake iteration failed")
            self.stop_event.wait(self.intake_interval)

    def _reconcile_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.coordinator.reconcile_once()
            except WorkflowConflictError:
                LOGGER.debug("Reconcile paused by evaluation maintenance")
            except Exception:
                LOGGER.exception("Reconcile iteration failed")
            self.stop_event.wait(self.reconcile_interval)
