from uuid import UUID

import httpx

from schema import LearningJob, LearningJobRequest, LearningResult


class LearningJobStore:
    def __init__(self, base_url: str, token: str, timeout_seconds: float = 30.0):
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_seconds,
        )

    def create(self, request: LearningJobRequest, idempotency_key: str) -> LearningJob:
        response = self.client.post(
            "/api/v1/internal/learning/jobs",
            headers={"Idempotency-Key": idempotency_key},
            json=request.model_dump(mode="json"),
        )
        response.raise_for_status()
        return LearningJob.model_validate(response.json())

    def get(self, job_id: UUID) -> LearningJob | None:
        response = self.client.get(f"/api/v1/internal/learning/jobs/{job_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return LearningJob.model_validate(response.json())

    def claim(self, owner: str, lease_seconds: int, max_attempts: int) -> LearningJob | None:
        response = self.client.post(
            "/api/v1/internal/execution/claim",
            json={
                "service": "learning",
                "owner": owner,
                "lease_seconds": lease_seconds,
                "max_attempts": max_attempts,
            },
        )
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return LearningJob.model_validate(response.json())

    def renew(self, job_id: UUID, owner: str, lease_seconds: int) -> bool:
        response = self.client.post(
            "/api/v1/internal/execution/renew",
            json={
                "service": "learning",
                "job_id": str(job_id),
                "owner": owner,
                "lease_seconds": lease_seconds,
            },
        )
        response.raise_for_status()
        return bool(response.json()["renewed"])

    def record_output(self, job_id, lease_owner, raw_output, result=None):
        response = self.client.post(
            f"/api/v1/internal/learning/jobs/{job_id}/output",
            json={"lease_owner": lease_owner, "raw_output": raw_output, "result": result},
        )
        response.raise_for_status()

    def succeed(self, job_id: UUID, result: LearningResult, raw: str) -> None:
        response = self.client.post(
            f"/api/v1/internal/learning/jobs/{job_id}/finish",
            json={
                "outcome": "succeeded",
                "result": result.model_dump(mode="json"),
                "raw_output": raw,
            },
        )
        response.raise_for_status()

    def fail(self, job_id: UUID, exc: Exception, max_attempts: int, *, raw_output=None, result=None) -> None:
        response = self.client.post(
            f"/api/v1/internal/learning/jobs/{job_id}/finish",
            json={
                "outcome": "failed",
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "raw_output": raw_output,
                "result": result,
                "max_attempts": max_attempts,
            },
        )
        response.raise_for_status()

    def close(self) -> None:
        self.client.close()
