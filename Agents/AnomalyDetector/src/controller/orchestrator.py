from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

import httpx

from schema.detection import Detection


class AgentOrchestratorSink:
    """Commit detector events to AgentOrchestrator with bounded retries."""

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout_seconds: float = 10,
        max_attempts: int = 3,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_seconds,
        )
        self._max_attempts = max_attempts

    @staticmethod
    def _identity(detection: Detection) -> str:
        stable = {
            "detected_at": detection.detected_at.isoformat() if detection.detected_at else None,
            "namespace": detection.metadata.namespace,
            "resource": detection.metadata.resource,
            "name": detection.metadata.name,
            "metric": detection.metadata.metric,
            "method": detection.method,
            "detail": detection.detail,
            "profile_id": detection.profile_id,
            "profile_version": detection.profile_version,
            "profile_parameters": detection.profile_parameters,
        }
        canonical = json.dumps(stable, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def envelope(self, detection: Detection) -> dict[str, Any]:
        detected_at = detection.detected_at or datetime.now(timezone.utc)
        return {
            "event_id": self._identity(detection),
            "detected_at": detected_at.isoformat(),
            "namespace": detection.metadata.namespace,
            "resource": detection.metadata.resource,
            "name": detection.metadata.name,
            "metric": detection.metadata.metric,
            "method": detection.method,
            "detail": detection.detail,
            "profile_id": detection.profile_id,
            "profile_version": detection.profile_version,
            "profile_parameters": detection.profile_parameters,
        }

    async def ingest(self, detections: list[Detection]) -> dict[str, int]:
        payload = {"anomalies": [self.envelope(item) for item in detections]}
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                response = await self._client.post("/api/v1/anomalies", json=payload)
                response.raise_for_status()
                result = response.json()
                if result.get("accepted", 0) + result.get("duplicates", 0) != len(detections):
                    raise ValueError("AgentOrchestrator did not acknowledge the complete batch")
                return result
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(min(2**attempt, 4))
        assert last_error is not None
        raise last_error

    async def close(self) -> None:
        await self._client.aclose()
