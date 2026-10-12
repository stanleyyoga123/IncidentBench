from typing import Any
from uuid import UUID

import httpx
from pydantic import TypeAdapter

from features.agent_workflow.schema import AnomalyEventInput, IngestionResponse, Workflow
from features.agent_workflow.schemas.pending_claim_response import PendingClaimResponse
from infrastructure.workflow_conflict_error import WorkflowConflictError
from infrastructure.persistence_unavailable_error import PersistenceUnavailableError


class WorkflowStoreClient:
    """Authenticated persistence boundary owned by EvaluationPlatform."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, body: Any = None) -> httpx.Response:
        try:
            response = self._client.request(
                method, f"/api/v1/internal/orchestration{path}", json=body,
            )
        except httpx.TransportError as exc:
            raise PersistenceUnavailableError("evaluation persistence transport failed") from exc
        if response.status_code >= 500:
            raise PersistenceUnavailableError(f"evaluation persistence returned HTTP {response.status_code}")
        if response.status_code == 409:
            raise WorkflowConflictError(response.json()["detail"])
        response.raise_for_status()
        return response

    def ingest(self, anomalies: list[AnomalyEventInput]) -> tuple[int, int, list[dict[str, Any]]]:
        result = IngestionResponse.model_validate(self._request(
            "POST", "/anomalies", {"anomalies": [item.model_dump(mode="json") for item in anomalies]},
        ).json())
        return result.accepted, result.duplicates, [item.model_dump() for item in result.records]

    def execution_available(self) -> bool:
        return TypeAdapter(bool).validate_python(self._request("GET", "/execution/available").json())

    def claim_pending(self, limit: int) -> tuple[Workflow, list[dict[str, Any]]] | None:
        response = self._request("POST", "/workflows/claim", {"limit": limit})
        if response.status_code == 204:
            return None
        result = PendingClaimResponse.model_validate(response.json())
        return result.workflow, result.anomalies

    def list_workflows(self) -> list[Workflow]:
        return TypeAdapter(list[Workflow]).validate_python(self._request("GET", "/workflows").json())

    def list_reconcilable(self) -> list[Workflow]:
        return TypeAdapter(list[Workflow]).validate_python(self._request("GET", "/workflows/reconcilable").json())

    def get_workflow(self, workflow_id: UUID) -> Workflow | None:
        try:
            response = self._request("GET", f"/workflows/{workflow_id}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return Workflow.model_validate(response.json())

    def anomaly_payloads(self, workflow_id: UUID) -> list[dict[str, Any]]:
        return TypeAdapter(list[dict[str, Any]]).validate_python(
            self._request("GET", f"/workflows/{workflow_id}/anomalies").json(),
        )

    def tool_calls_for_workflow(self, workflow: Workflow) -> list[dict[str, Any]]:
        return TypeAdapter(list[dict[str, Any]]).validate_python(
            self._request("GET", f"/workflows/{workflow.id}/tool-calls").json(),
        )

    def retrieve_lessons(self, anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return TypeAdapter(list[dict[str, Any]]).validate_python(
            self._request("POST", "/lessons/retrieve", {"anomalies": anomalies}).json(),
        )

    def decide(self, workflow_id: UUID, decision: str, actor: str, reason: str, expected_version: int) -> Workflow:
        response = self._mutation("POST", f"/workflows/{workflow_id}/decision", {
            "decision": decision, "actor": actor, "reason": reason, "expected_version": expected_version,
        })
        return Workflow.model_validate(response.json())

    def reset_for_retry(self, workflow_id: UUID, expected_version: int, actor: str, reason: str) -> Workflow:
        response = self._mutation("POST", f"/workflows/{workflow_id}/retry", {
            "actor": actor, "reason": reason, "expected_version": expected_version,
        })
        return Workflow.model_validate(response.json())

    def _mutation(self, method: str, path: str, body: dict[str, Any]) -> httpx.Response:
        try:
            return self._request(method, path, body)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise KeyError("workflow not found") from exc
            raise

    def attach_rca_job(self, workflow_id: UUID, job_id: UUID) -> None:
        self._mutation("POST", f"/workflows/{workflow_id}/rca/attach", {"job_id": str(job_id)})

    def attach_remediation_job(self, workflow_id: UUID, job_id: UUID) -> None:
        self._mutation("POST", f"/workflows/{workflow_id}/remediation/attach", {"job_id": str(job_id)})

    def attach_learning_job(self, workflow_id: UUID, job_id: UUID) -> None:
        self._mutation("POST", f"/workflows/{workflow_id}/learning/attach", {"job_id": str(job_id)})

    def set_rca_state(self, workflow_id: UUID, status: str, *, result=None, error=None) -> None:
        self._mutation("POST", f"/workflows/{workflow_id}/rca/state", {"status": status, "result": result, "error": error})

    def set_remediation_state(self, workflow_id: UUID, status: str, *, error=None) -> None:
        self._mutation("POST", f"/workflows/{workflow_id}/remediation/state", {"status": status, "error": error})

    def set_learning_state(self, workflow_id: UUID, status: str, *, error=None) -> None:
        self._mutation("POST", f"/workflows/{workflow_id}/learning/state", {"status": status, "error": error})

    def fail_submission(self, workflow_id: UUID, error: dict[str, Any]) -> None:
        self._mutation("POST", f"/workflows/{workflow_id}/submission-failed", {"error": error})

    def mark_submission_failed(self, workflow_id: UUID, error: dict[str, Any]) -> None:
        self._mutation("POST", f"/workflows/{workflow_id}/downstream-failed", {"error": error})

    def finish_remediation_job(self, job_id: UUID, status: str, *, error=None) -> None:
        try:
            response = self._client.post(
                f"/api/v1/internal/remediation/jobs/{job_id}/finish", json={"status": status, "error": error},
            )
        except httpx.TransportError as exc:
            raise PersistenceUnavailableError("evaluation persistence transport failed") from exc
        if response.status_code >= 500:
            raise PersistenceUnavailableError(f"evaluation persistence returned HTTP {response.status_code}")
        if response.status_code == 409:
            raise WorkflowConflictError(response.json()["detail"])
        response.raise_for_status()
