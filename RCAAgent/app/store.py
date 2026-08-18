from typing import Any
from uuid import UUID

import httpx

from schema import RCAJob, RCAJobRequest, RCAResult


class RCAJobStore:
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

    def create(self, request: RCAJobRequest, idempotency_key: str) -> RCAJob:
        response = self._client.post(
            "/api/v1/internal/rca/jobs",
            headers={"Idempotency-Key": idempotency_key},
            json=request.model_dump(mode="json"),
        )
        response.raise_for_status()
        return RCAJob.model_validate(response.json())

    def get(self, job_id: UUID) -> RCAJob | None:
        response = self._client.get(f"/api/v1/internal/rca/jobs/{job_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return RCAJob.model_validate(response.json())

    def claim(self, owner: str, lease_seconds: int, max_attempts: int) -> RCAJob | None:
        response = self._client.post(
            "/api/v1/internal/execution/claim",
            json={
                "service": "rca",
                "owner": owner,
                "lease_seconds": lease_seconds,
                "max_attempts": max_attempts,
            },
        )
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return RCAJob.model_validate(response.json())

    def succeed(self, job_id: UUID, result: RCAResult, raw_output: str) -> None:
        response = self._client.post(
            f"/api/v1/internal/rca/jobs/{job_id}/finish",
            json={
                "outcome": "succeeded",
                "result": result.model_dump(mode="json"),
                "raw_output": raw_output,
            },
        )
        response.raise_for_status()

    def renew(self, job_id: UUID, owner: str, lease_seconds: int) -> bool:
        response = self._client.post(
            "/api/v1/internal/execution/renew",
            json={
                "service": "rca",
                "job_id": str(job_id),
                "owner": owner,
                "lease_seconds": lease_seconds,
            },
        )
        response.raise_for_status()
        return bool(response.json()["renewed"])

    def fail(self, job: RCAJob, exc: Exception, max_attempts: int) -> None:
        response = self._client.post(
            f"/api/v1/internal/rca/jobs/{job.id}/finish",
            json={
                "outcome": "failed",
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "max_attempts": max_attempts,
            },
        )
        response.raise_for_status()

    def record_tool_call(self, job_id: UUID, name: str, arguments: dict, result: Any) -> None:
        response = self._client.post(
            f"/api/v1/internal/rca/jobs/{job_id}/tool-calls",
            json={"tool_name": name, "arguments": arguments, "result": result},
        )
        response.raise_for_status()
