from typing import Any
from uuid import UUID
import hashlib
import json

import httpx

from schema import DownstreamJob


class AgentClient:
    def __init__(self, base_url: str, token: str, timeout_seconds: float = 30):
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_seconds,
        )

    def create_rca(
        self,
        workflow_id: UUID,
        anomalies: list[dict[str, Any]],
        attempt: int = 1,
        historical_lessons: list[dict[str, Any]] | None = None,
    ) -> DownstreamJob:
        response = self._client.post(
            "/api/v1/rca/jobs",
            headers={"Idempotency-Key": f"workflow:{workflow_id}:rca:{attempt}"},
            json={
                "workflow_id": str(workflow_id),
                "anomalies": anomalies,
                "historical_lessons": historical_lessons or [],
            },
        )
        response.raise_for_status()
        return DownstreamJob.model_validate(response.json())

    def get_rca(self, job_id: UUID) -> DownstreamJob:
        response = self._client.get(f"/api/v1/rca/jobs/{job_id}")
        response.raise_for_status()
        return DownstreamJob.model_validate(response.json())

    def create_remediation(
        self,
        workflow_id: UUID,
        rca_job: DownstreamJob,
        approval: dict[str, Any],
        attempt: int = 1,
    ) -> DownstreamJob:
        canonical = json.dumps(rca_job.result, sort_keys=True, separators=(",", ":"))
        result_hash = hashlib.sha256(canonical.encode()).hexdigest()
        response = self._client.post(
            "/api/v1/remediation/jobs",
            headers={"Idempotency-Key": f"workflow:{workflow_id}:remediation:{attempt}"},
            json={
                "workflow_id": str(workflow_id),
                "rca_job_id": str(rca_job.id),
                "rca_result": rca_job.result,
                "rca_result_sha256": result_hash,
                "approval": approval,
            },
        )
        response.raise_for_status()
        return DownstreamJob.model_validate(response.json())

    def get_remediation(self, job_id: UUID) -> DownstreamJob:
        response = self._client.get(f"/api/v1/remediation/jobs/{job_id}")
        response.raise_for_status()
        return DownstreamJob.model_validate(response.json())

    def create_learning(
        self,
        workflow_id: UUID,
        source: dict[str, Any],
        attempt: int = 1,
    ) -> DownstreamJob:
        canonical = json.dumps(source, sort_keys=True, separators=(",", ":"))
        source_hash = hashlib.sha256(canonical.encode()).hexdigest()
        response = self._client.post(
            "/api/v1/learning/jobs",
            headers={"Idempotency-Key": f"workflow:{workflow_id}:learning:{attempt}"},
            json={
                "workflow_id": str(workflow_id),
                "source": source,
                "source_sha256": source_hash,
            },
        )
        response.raise_for_status()
        return DownstreamJob.model_validate(response.json())

    def get_learning(self, job_id: UUID) -> DownstreamJob:
        response = self._client.get(f"/api/v1/learning/jobs/{job_id}")
        response.raise_for_status()
        return DownstreamJob.model_validate(response.json())

    def close(self) -> None:
        self._client.close()
