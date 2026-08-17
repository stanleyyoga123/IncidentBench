from __future__ import annotations

import asyncio
import secrets
import threading
from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from adaptation import (
    DetectorProfile,
    DetectorProfileRegistry,
    ProfileConflictError,
    ProfileNotFoundError,
    ProfileValidationError,
)
from adaptation.profile import DetectorMethod
from common.logger import get_logger
from config import SETTINGS
from manager.detector import DetectorManager


LOGGER = get_logger("DetectorAPI")


class ProfileCollection(BaseModel):
    persistence: str
    count: int
    profiles: list[DetectorProfile]


class ProfileHistory(BaseModel):
    persistence: str
    profile_id: str
    revisions: list[DetectorProfile]


class ProfileCreateRequest(BaseModel):
    method: DetectorMethod
    resource: str = "*"
    name: str = "*"
    metric: str = Field(min_length=1)
    parameters: dict[str, Any]
    reason: str = Field(min_length=3)


class ProfileUpdateRequest(BaseModel):
    parameters: dict[str, Any]
    reason: str = Field(min_length=3)
    expected_version: int | None = Field(default=None, ge=1)


class ProfileResetRequest(BaseModel):
    reason: str = Field(min_length=3)
    expected_version: int | None = Field(default=None, ge=1)


def create_app(
    *,
    registry: DetectorProfileRegistry | None = None,
    manager_factory: Callable[[DetectorProfileRegistry], DetectorManager] | None = None,
    start_detector: bool = True,
    profile_api_token: str | None = None,
) -> FastAPI:
    profile_registry = registry or DetectorProfileRegistry()
    factory = manager_factory or (
        lambda profiles: DetectorManager(profile_registry=profiles)
    )
    configured_token = (
        SETTINGS.detector.profile_api_token
        if profile_api_token is None
        else profile_api_token
    )
    detector_task: asyncio.Task | None = None
    detector_stop_event: threading.Event | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal detector_task, detector_stop_event
        if start_detector:
            manager = factory(profile_registry)
            detector_stop_event = threading.Event()
            detector_task = asyncio.create_task(
                manager.detect_forever(detector_stop_event),
                name="anomaly-detector-loop",
            )
            app.state.detector_manager = manager
        yield
        if detector_stop_event is not None:
            detector_stop_event.set()
        if detector_task is not None:
            try:
                await detector_task
            except Exception:
                LOGGER.exception("Detector loop failed during API lifetime")

    app = FastAPI(
        title="AnomalyDetector Control API",
        description=(
            "Inspect and safely change the runtime profiles used by the "
            "Kubernetes anomaly detectors. Profile mutations are bounded, "
            "versioned, token-protected, and currently in-memory."
        ),
        version="1.0.0",
        lifespan=lifespan,
        openapi_tags=[
            {
                "name": "status",
                "description": "Process and detector-loop readiness.",
            },
            {
                "name": "detector-profiles",
                "description": (
                    "Resolve, inspect, create, update, and reset bounded "
                    "detector profiles."
                ),
            },
        ],
    )
    app.state.profile_registry = profile_registry

    def require_profile_token(
        x_detector_profile_token: str | None = Header(default=None),
    ) -> None:
        if not configured_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="detector profile mutations are disabled",
            )
        if x_detector_profile_token is None or not secrets.compare_digest(
            x_detector_profile_token,
            configured_token,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid detector profile token",
            )

    @app.get(
        "/health",
        operation_id="get_anomaly_detector_health",
        summary="Get detector health",
        tags=["status"],
    )
    def health(response: Response) -> dict[str, Any]:
        """Report API health, detector-loop state, and mutation availability."""
        task_failed = detector_task is not None and detector_task.done()
        if task_failed:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "degraded" if task_failed else "ok",
            "detector_loop": (
                "disabled"
                if not start_detector
                else "failed" if task_failed else "running"
            ),
            "profile_persistence": profile_registry.persistence,
            "active_profiles": len(profile_registry.list_active()),
            "mutations_enabled": bool(configured_token),
        }

    @app.get(
        "/api/v1/detector/profiles",
        response_model=ProfileCollection,
        operation_id="list_detector_profiles",
        summary="List active detector profiles",
        tags=["detector-profiles"],
    )
    def list_profiles() -> ProfileCollection:
        """Return all active default and scoped runtime profiles."""
        profiles = profile_registry.list_active()
        return ProfileCollection(
            persistence=profile_registry.persistence,
            count=len(profiles),
            profiles=profiles,
        )

    @app.get(
        "/api/v1/detector/profiles/resolve",
        response_model=DetectorProfile,
        operation_id="resolve_detector_profile",
        summary="Resolve the effective profile for a metric series",
        tags=["detector-profiles"],
    )
    def resolve_profile(
        method: DetectorMethod,
        resource: str,
        name: str,
        metric: str,
    ) -> DetectorProfile:
        """Resolve exact scope, then resource wildcard, then global default."""
        profile = profile_registry.resolve(method, resource, name, metric)
        if profile is None:
            raise HTTPException(status_code=404, detail="no matching detector profile")
        return profile

    @app.get(
        "/api/v1/detector/profiles/{profile_id}/history",
        response_model=ProfileHistory,
        operation_id="get_detector_profile_history",
        summary="Get every revision of a profile",
        tags=["detector-profiles"],
    )
    def profile_history(profile_id: str) -> ProfileHistory:
        """Return immutable revisions ordered from oldest to newest."""
        try:
            revisions = profile_registry.history(profile_id)
        except ProfileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        return ProfileHistory(
            persistence=profile_registry.persistence,
            profile_id=profile_id,
            revisions=revisions,
        )

    @app.get(
        "/api/v1/detector/profiles/{profile_id}",
        response_model=DetectorProfile,
        operation_id="get_detector_profile",
        summary="Get the latest revision of a profile",
        tags=["detector-profiles"],
    )
    def get_profile(profile_id: str) -> DetectorProfile:
        """Return the latest revision, including a reset inactive override."""
        try:
            return profile_registry.get(profile_id)
        except ProfileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc

    @app.post(
        "/api/v1/detector/profiles",
        response_model=DetectorProfile,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_profile_token)],
        operation_id="create_detector_profile_override",
        summary="Create a scoped detector-profile override",
        tags=["detector-profiles"],
    )
    def create_profile(request: ProfileCreateRequest) -> DetectorProfile:
        """Inherit an effective profile and override only supplied parameters."""
        try:
            return profile_registry.create_override(
                method=request.method,
                resource=request.resource,
                name=request.name,
                metric=request.metric,
                changes=request.parameters,
                reason=request.reason,
            )
        except ProfileConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ProfileValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.patch(
        "/api/v1/detector/profiles/{profile_id}",
        response_model=DetectorProfile,
        dependencies=[Depends(require_profile_token)],
        operation_id="update_detector_profile",
        summary="Update bounded parameters on an active profile",
        tags=["detector-profiles"],
    )
    def update_profile(
        profile_id: str,
        request: ProfileUpdateRequest,
    ) -> DetectorProfile:
        """Create a new revision; use expected_version to reject stale writes."""
        try:
            return profile_registry.update(
                profile_id,
                changes=request.parameters,
                reason=request.reason,
                expected_version=request.expected_version,
            )
        except ProfileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        except ProfileConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ProfileValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/api/v1/detector/profiles/{profile_id}/reset",
        response_model=DetectorProfile,
        dependencies=[Depends(require_profile_token)],
        operation_id="reset_detector_profile",
        summary="Reset a default or deactivate a scoped override",
        tags=["detector-profiles"],
    )
    def reset_profile(
        profile_id: str,
        request: ProfileResetRequest,
    ) -> DetectorProfile:
        """Restore a global default or deactivate an override to resume inheritance."""
        try:
            return profile_registry.reset(
                profile_id,
                reason=request.reason,
                expected_version=request.expected_version,
            )
        except ProfileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        except ProfileConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ProfileValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app
