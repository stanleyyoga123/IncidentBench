from typing import Any
from uuid import UUID

import httpx

from schema import RemediationJob, RemediationJobRequest, RemediationResult


class RemediationJobStore:
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ):
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_seconds,
        )

    def create(self, request: RemediationJobRequest, key: str) -> RemediationJob:
        response = self._client.post(
            "/api/v1/internal/remediation/jobs",
            headers={"Idempotency-Key": key},
            json=request.model_dump(mode="json"),
        )
        response.raise_for_status()
        return RemediationJob.model_validate(response.json())

    def get(self, job_id: UUID) -> RemediationJob | None:
        response = self._client.get(f"/api/v1/internal/remediation/jobs/{job_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return RemediationJob.model_validate(response.json())

    def claim(self, owner: str, lease_seconds: int) -> RemediationJob | None:
        response = self._client.post(
            "/api/v1/internal/execution/claim",
            json={
                "service": "remediation",
                "owner": owner,
                "lease_seconds": lease_seconds,
                "max_attempts": 3,
            },
        )
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return RemediationJob.model_validate(response.json())

    def succeed(self, job_id: UUID, result: RemediationResult, raw: str) -> None:
        response = self._client.post(
            f"/api/v1/internal/remediation/jobs/{job_id}/finish",
            json={
                "status": "succeeded",
                "result": result.model_dump(mode="json"),
                "raw_output": raw,
            },
        )
        response.raise_for_status()

    def renew(self, job_id: UUID, owner: str, lease_seconds: int) -> bool:
        response = self._client.post(
            "/api/v1/internal/execution/renew",
            json={
                "service": "remediation",
                "job_id": str(job_id),
                "owner": owner,
                "lease_seconds": lease_seconds,
            },
        )
        response.raise_for_status()
        return bool(response.json()["renewed"])

    def needs_review(self, job_id: UUID, exc: Exception) -> None:
        response = self._client.post(
            f"/api/v1/internal/remediation/jobs/{job_id}/finish",
            json={
                "status": "needs_review",
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
        )
        response.raise_for_status()

    def record_tool_call(self, job_id: UUID, name: str, args: dict, result: Any) -> None:
        response = self._client.post(
            f"/api/v1/internal/remediation/jobs/{job_id}/tool-calls",
            json={"tool_name": name, "arguments": args, "result": result},
        )
        response.raise_for_status()

    def list_artifacts(self, job_id: UUID) -> list[str]:
        response = self._client.get(
            f"/api/v1/internal/remediation/jobs/{job_id}/artifacts"
        )
        response.raise_for_status()
        return list(response.json()["filenames"])
