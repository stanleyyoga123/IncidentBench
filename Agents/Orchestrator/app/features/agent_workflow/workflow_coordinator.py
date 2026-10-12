from functools import wraps
from threading import RLock
import logging
import json
from typing import Any
from uuid import UUID

import httpx

from features.agent_workflow.agent_client import AgentClient
from features.agent_workflow.schema import DecisionRequest, RetryRequest, Workflow
from features.agent_workflow.workflow_store_client import WorkflowStoreClient
from infrastructure.workflow_conflict_error import WorkflowConflictError
from infrastructure.persistence_unavailable_error import PersistenceUnavailableError
from infrastructure.maintenance_gate import MaintenanceGate


LOGGER = logging.getLogger("AgentOrchestrator")
AUTO_APPROVAL_ACTOR = "agent-orchestrator"
AUTO_APPROVAL_REASON = "automatic approval after RCA required remediation"


def running_only(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self._lifecycle_lock, self._maintenance_gate.running():
            return method(self, *args, **kwargs)

    return guarded


class WorkflowCoordinator:
    def __init__(
        self,
        store: WorkflowStoreClient,
        rca: AgentClient,
        remediator: AgentClient,
        learning: AgentClient,
        maintenance_gate: MaintenanceGate,
        *,
        batch_size: int,
    ) -> None:
        self._lifecycle_lock = RLock()
        self._maintenance_gate = maintenance_gate
        self._store = store
        self._rca = rca
        self._remediator = remediator
        self._learning = learning
        self._batch_size = batch_size

    @running_only
    def intake_once(self) -> int:
        if not self._store.execution_available():
            return 0
        claimed = self._store.claim_pending(self._batch_size)
        if claimed is None:
            return 0
        workflow, anomalies = claimed
        try:
            self._submit_rca(workflow, anomalies)
            return len(anomalies)
        except (PersistenceUnavailableError, WorkflowConflictError):
            raise
        except Exception as exc:
            if self._ambiguous_downstream_failure(exc):
                raise
            self._store.fail_submission(workflow.id, self._error(exc))
            LOGGER.exception("Failed to submit RCA workflow %s", workflow.id)
            return 0

    def _submit_rca(self, workflow: Workflow, anomalies: list[dict[str, Any]]) -> None:
        attempt = workflow.version if workflow.rca_job_id is not None else 1
        if workflow.rca_job_id is None:
            lessons = self._store.retrieve_lessons(anomalies)
            job = self._rca.create_rca(workflow.id, anomalies, attempt, historical_lessons=lessons)
        else:
            job = self._rca.create_rca(workflow.id, anomalies, attempt)
        self._store.attach_rca_job(workflow.id, job.id)

    def _submit_remediation(self, workflow: Workflow) -> Workflow:
        if workflow.decision_actor is None or workflow.decision_reason is None:
            raise ValueError("remediation submission requires persisted approval")
        rca_job = self._rca.get_rca(workflow.rca_job_id)
        attempt = workflow.version if workflow.remediation_job_id is not None else 1
        job = self._remediator.create_remediation(
            workflow.id,
            rca_job,
            {"actor": workflow.decision_actor, "reason": workflow.decision_reason,
             "workflow_version": workflow.version},
            attempt,
        )
        self._store.attach_remediation_job(workflow.id, job.id)
        return self._store.get_workflow(workflow.id)

    def _recover_submission(self, workflow: Workflow) -> None:
        try:
            if workflow.status == "rca_submitting":
                self._submit_rca(workflow, self._store.anomaly_payloads(workflow.id))
            else:
                self._submit_remediation(workflow)
        except (PersistenceUnavailableError, WorkflowConflictError):
            raise
        except Exception as exc:
            if self._ambiguous_downstream_failure(exc):
                raise
            if workflow.status == "rca_submitting" and workflow.rca_job_id is None:
                self._store.fail_submission(workflow.id, self._error(exc))
            else:
                self._store.mark_submission_failed(workflow.id, self._error(exc))
            raise

    @staticmethod
    def _ambiguous_downstream_failure(exc: Exception) -> bool:
        return isinstance(exc, httpx.TransportError) or (
            isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500
        )

    @running_only
    def submit_approved_remediation(
        self,
        workflow_id: UUID,
        actor: str,
        reason: str,
        expected_version: int,
    ) -> Workflow:
        workflow = self._store.decide(
            workflow_id, "approved", actor, reason, expected_version
        )
        try:
            return self._submit_remediation(workflow)
        except (PersistenceUnavailableError, WorkflowConflictError):
            raise
        except Exception as exc:
            if self._ambiguous_downstream_failure(exc):
                raise
            self._store.mark_submission_failed(workflow.id, self._error(exc))
            raise

    @running_only
    def submit_learning(self, workflow: Workflow) -> Workflow:
        rca_job = self._rca.get_rca(workflow.rca_job_id)
        remediation_job = (
            self._remediator.get_remediation(workflow.remediation_job_id)
            if workflow.remediation_job_id
            else None
        )
        source = self._json_safe(
            {
                "workflow_id": str(workflow.id),
                "completion_type": (
                    "remediated" if remediation_job is not None else "no_action"
                ),
                "anomalies": self._store.anomaly_payloads(workflow.id),
                "rca": {
                    "job_id": str(rca_job.id),
                    "result": rca_job.result,
                },
                "remediation": (
                    {
                        "job_id": str(remediation_job.id),
                        "result": remediation_job.result,
                    }
                    if remediation_job is not None
                    else None
                ),
                "tool_calls": self._bounded_tool_calls(
                    self._store.tool_calls_for_workflow(workflow)
                ),
            }
        )
        job = self._learning.create_learning(workflow.id, source)
        self._store.attach_learning_job(workflow.id, job.id)
        return self._store.get_workflow(workflow.id)

    @running_only
    def reconcile_once(self) -> int:
        updated = 0
        for workflow in self._store.list_reconcilable():
            try:
                if workflow.status in {"rca_submitting", "remediation_submitting"}:
                    self._recover_submission(workflow)
                    updated += 1
                elif workflow.status == "awaiting_approval":
                    self.submit_approved_remediation(
                        workflow.id,
                        AUTO_APPROVAL_ACTOR,
                        AUTO_APPROVAL_REASON,
                        workflow.version,
                    )
                    updated += 1
                elif workflow.status.startswith("rca_") and workflow.rca_job_id:
                    job = self._rca.get_rca(workflow.rca_job_id)
                    expected = (
                        "rca_running" if job.status == "running" else "rca_queued"
                    )
                    if (
                        job.status in {"queued", "running"}
                        and workflow.status == expected
                    ):
                        continue
                    self._store.set_rca_state(
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
                        current = self._store.get_workflow(workflow.id)
                        if current is not None:
                            self.submit_approved_remediation(
                                current.id,
                                AUTO_APPROVAL_ACTOR,
                                AUTO_APPROVAL_REASON,
                                current.version,
                            )
                    elif job.status == "succeeded":
                        current = self._store.get_workflow(workflow.id)
                        if current is not None:
                            self.submit_learning(current)
                elif (
                    workflow.status.startswith("remediation_")
                    or workflow.status == "needs_review"
                ) and workflow.remediation_job_id:
                    job = self._remediator.get_remediation(workflow.remediation_job_id)
                    if job.status == "needs_review":
                        # Finish legacy review records automatically during rolling upgrades.
                        self._store.finish_remediation_job(
                            job.id, "failed", error=job.error
                        )
                    expected = (
                        "remediation_running"
                        if job.status == "running"
                        else "remediation_queued"
                    )
                    if (
                        job.status in {"queued", "running"}
                        and workflow.status == expected
                    ):
                        continue
                    self._store.set_remediation_state(
                        workflow.id,
                        job.status,
                        error=job.error,
                    )
                    updated += 1
                    if job.status == "succeeded":
                        current = self._store.get_workflow(workflow.id)
                        if current is not None:
                            self.submit_learning(current)
                elif workflow.status == "learning_submitting":
                    self.submit_learning(workflow)
                    updated += 1
                elif (
                    workflow.status.startswith("learning_") and workflow.learning_job_id
                ):
                    job = self._learning.get_learning(workflow.learning_job_id)
                    expected = (
                        "learning_running"
                        if job.status == "running"
                        else "learning_queued"
                    )
                    if (
                        job.status in {"queued", "running"}
                        and workflow.status == expected
                    ):
                        continue
                    self._store.set_learning_state(
                        workflow.id, job.status, error=job.error
                    )
                    updated += 1
            except (httpx.HTTPError, ValueError, WorkflowConflictError, PersistenceUnavailableError):
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
                    "arguments_excerpt": json.dumps(item.get("arguments"), default=str)[
                        :1_000
                    ],
                    "result_excerpt": json.dumps(item.get("result"), default=str)[
                        :2_000
                    ],
                    "truncated": True,
                }
            bounded.append(item)
        return bounded

    def enrich(
        self, workflow: Workflow, *, include_anomalies: bool = False
    ) -> Workflow:
        updates = {}
        if include_anomalies:
            updates["anomalies"] = self._store.anomaly_payloads(workflow.id)
        try:
            if workflow.rca_job_id:
                updates["rca_result"] = self._rca.get_rca(workflow.rca_job_id).result
            if workflow.remediation_job_id:
                updates["remediation_result"] = self._remediator.get_remediation(
                    workflow.remediation_job_id
                ).result
            if workflow.learning_job_id:
                updates["learning_result"] = self._learning.get_learning(
                    workflow.learning_job_id
                ).result
        except (httpx.HTTPError, ValueError):
            # Persisted state remains inspectable during a downstream outage.
            pass
        return workflow.model_copy(update=updates)

    @running_only
    def decide(
        self, workflow_id: UUID, request: DecisionRequest, value: str
    ) -> Workflow:
        if value == "approved":
            return self.submit_approved_remediation(
                workflow_id, request.actor, request.reason, request.expected_version
            )
        try:
            return self._store.decide(
                workflow_id,
                value,
                request.actor,
                request.reason,
                request.expected_version,
            )
        except (KeyError, WorkflowConflictError, PersistenceUnavailableError):
            raise
        except Exception as exc:
            self._store.mark_submission_failed(workflow_id, self._error(exc))
            raise

    @running_only
    def retry(self, workflow_id: UUID, request: RetryRequest) -> Workflow:
        try:
            workflow = self._store.reset_for_retry(
                workflow_id, request.expected_version, request.actor, request.reason,
            )
            if workflow.status == "rca_submitting":
                self._submit_rca(workflow, self._store.anomaly_payloads(workflow.id))
                return self._store.get_workflow(workflow.id)
            return self._submit_remediation(workflow)
        except (KeyError, WorkflowConflictError, PersistenceUnavailableError):
            raise
        except Exception as exc:
            if self._ambiguous_downstream_failure(exc):
                raise
            self._store.mark_submission_failed(workflow_id, self._error(exc))
            raise
