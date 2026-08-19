import secrets
from contextlib import asynccontextmanager
from typing import Callable
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse

from clients import AgentClient
from config import Settings, get_settings
from schema import (
    AnomalyBatchRequest,
    ArtifactListResponse,
    ArtifactUpsertRequest,
    DecisionRequest,
    ExecutionClaimRequest,
    ExecutionRenewRequest,
    IngestionResponse,
    IncidentLesson,
    LearningFinishRequest,
    LearningJob,
    LearningJobCreateRequest,
    LessonCollection,
    LessonStatusRequest,
    RCAFinishRequest,
    RCAJob,
    RCAJobCreateRequest,
    RemediationFinishRequest,
    RemediationJob,
    RemediationJobCreateRequest,
    RenewResponse,
    RetryRequest,
    ToolCallRequest,
    Workflow,
    WorkflowCollection,
)
from service import CoordinatorLoops, WorkflowCoordinator
from store import WorkflowConflictError, WorkflowStore


def _bearer(expected: str) -> Callable:
    def authorize(authorization: str | None = Header(default=None)) -> None:
        prefix = "Bearer "
        supplied = authorization[len(prefix):] if authorization and authorization.startswith(prefix) else ""
        if not supplied or not secrets.compare_digest(supplied, expected):
            raise HTTPException(status_code=401, detail="invalid bearer token")
    return authorize


def create_app(
    settings: Settings | None = None,
    *,
    start_loops: bool = True,
    store: WorkflowStore | None = None,
    rca: AgentClient | None = None,
    remediator: AgentClient | None = None,
    learning: AgentClient | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    store = store or WorkflowStore(settings.database.dsn)
    rca = rca or AgentClient(**settings.rca.model_dump())
    remediator = remediator or AgentClient(**settings.remediator.model_dump())
    learning = learning or AgentClient(**settings.learning.model_dump())
    coordinator = WorkflowCoordinator(
        store, rca, remediator, learning, batch_size=settings.scheduler.batch_size
    )
    loops = CoordinatorLoops(
        coordinator,
        settings.scheduler.intake_interval_seconds,
        settings.scheduler.reconcile_interval_seconds,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if start_loops:
            loops.start()
        yield
        if start_loops:
            loops.stop()
        rca.close()
        remediator.close()
        learning.close()

    app = FastAPI(
        title="AgentOrchestrator API",
        version="1.0.0",
        description="Durable anomaly ingestion and RCA/remediation coordination.",
        lifespan=lifespan,
    )
    ingest_auth = Depends(_bearer(settings.api.ingestion_token))
    control_auth = Depends(_bearer(settings.api.control_token))
    store_auth = Depends(_bearer(settings.api.store_token))

    @app.get("/health", operation_id="get_agent_orchestrator_health")
    def health() -> dict:
        return {"status": "ok", "active_execution_available": store.execution_available()}

    @app.post(
        "/api/v1/anomalies",
        response_model=IngestionResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[ingest_auth],
        operation_id="ingest_anomaly_events",
    )
    def ingest(request: AnomalyBatchRequest) -> IngestionResponse:
        accepted, duplicates, records = store.ingest(request.anomalies)
        return IngestionResponse(
            accepted=accepted,
            duplicates=duplicates,
            event_ids=[item.event_id for item in request.anomalies],
            records=records,
        )

    @app.get(
        "/api/v1/workflows",
        response_model=WorkflowCollection,
        dependencies=[control_auth],
        operation_id="list_agent_workflows",
    )
    def list_workflows() -> WorkflowCollection:
        return WorkflowCollection(
            workflows=[enrich(workflow) for workflow in store.list_workflows()]
        )

    def enrich(workflow: Workflow, *, include_anomalies: bool = False) -> Workflow:
        updates = {}
        if include_anomalies:
            updates["anomalies"] = store.anomaly_payloads(workflow.id)
        try:
            if workflow.rca_job_id:
                updates["rca_result"] = rca.get_rca(workflow.rca_job_id).result
            if workflow.remediation_job_id:
                updates["remediation_result"] = remediator.get_remediation(
                    workflow.remediation_job_id
                ).result
            if workflow.learning_job_id:
                updates["learning_result"] = learning.get_learning(
                    workflow.learning_job_id
                ).result
        except Exception:
            # Persisted state remains inspectable during a downstream outage.
            pass
        return workflow.model_copy(update=updates)

    @app.get(
        "/api/v1/workflows/{workflow_id}",
        response_model=Workflow,
        dependencies=[control_auth],
        operation_id="get_agent_workflow",
    )
    def get_workflow(workflow_id: UUID) -> Workflow:
        workflow = store.get_workflow(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        return enrich(workflow, include_anomalies=True)

    @app.get(
        "/api/v1/lessons",
        response_model=LessonCollection,
        dependencies=[control_auth],
        operation_id="list_incident_lessons",
    )
    def list_lessons(active: bool | None = None) -> LessonCollection:
        return LessonCollection(lessons=store.list_lessons(active=active))

    @app.get(
        "/api/v1/lessons/{lesson_id}",
        response_model=IncidentLesson,
        dependencies=[control_auth],
        operation_id="get_incident_lesson",
    )
    def get_lesson(lesson_id: UUID) -> IncidentLesson:
        lesson = store.get_lesson(lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail="lesson not found")
        return lesson

    def set_lesson_status(
        lesson_id: UUID, request: LessonStatusRequest, active: bool
    ) -> IncidentLesson:
        try:
            return store.set_lesson_active(
                lesson_id,
                active,
                request.actor,
                request.reason,
                request.expected_version,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="lesson not found") from exc
        except WorkflowConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/v1/lessons/{lesson_id}/enable",
        response_model=IncidentLesson,
        dependencies=[control_auth],
        operation_id="enable_incident_lesson",
    )
    def enable_lesson(lesson_id: UUID, request: LessonStatusRequest) -> IncidentLesson:
        return set_lesson_status(lesson_id, request, True)

    @app.post(
        "/api/v1/lessons/{lesson_id}/disable",
        response_model=IncidentLesson,
        dependencies=[control_auth],
        operation_id="disable_incident_lesson",
    )
    def disable_lesson(lesson_id: UUID, request: LessonStatusRequest) -> IncidentLesson:
        return set_lesson_status(lesson_id, request, False)

    def decision(workflow_id: UUID, request: DecisionRequest, value: str) -> Workflow:
        try:
            if value == "approved":
                return coordinator.submit_approved_remediation(
                    workflow_id,
                    request.actor,
                    request.reason,
                    request.expected_version,
                )
            return store.decide(
                workflow_id, value, request.actor, request.reason, request.expected_version
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="workflow not found") from exc
        except WorkflowConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            if value != "approved":
                store.mark_submission_failed(
                    workflow_id,
                    {"type": type(exc).__name__, "message": str(exc)},
                )
            raise HTTPException(status_code=502, detail="downstream job submission failed") from exc

    @app.post(
        "/api/v1/workflows/{workflow_id}/approve",
        response_model=Workflow,
        dependencies=[control_auth],
        operation_id="approve_agent_workflow",
    )
    def approve(workflow_id: UUID, request: DecisionRequest) -> Workflow:
        return decision(workflow_id, request, "approved")

    @app.post(
        "/api/v1/workflows/{workflow_id}/decline",
        response_model=Workflow,
        dependencies=[control_auth],
        operation_id="decline_agent_workflow",
    )
    def decline(workflow_id: UUID, request: DecisionRequest) -> Workflow:
        return decision(workflow_id, request, "declined")

    @app.post(
        "/api/v1/workflows/{workflow_id}/retry",
        response_model=Workflow,
        dependencies=[control_auth],
        operation_id="retry_agent_workflow",
    )
    def retry(workflow_id: UUID, request: RetryRequest) -> Workflow:
        try:
            workflow = store.reset_for_retry(
                workflow_id,
                request.expected_version,
                request.actor,
                request.reason,
            )
            attempt = workflow.version
            if workflow.status == "rca_submitting":
                job = rca.create_rca(
                    workflow.id, store.anomaly_payloads(workflow.id), attempt
                )
                store.attach_rca_job(workflow.id, job.id)
            else:
                rca_job = rca.get_rca(workflow.rca_job_id)
                job = remediator.create_remediation(
                    workflow.id,
                    rca_job,
                    {"actor": request.actor, "reason": request.reason,
                     "workflow_version": workflow.version},
                    attempt,
                )
                store.attach_remediation_job(workflow.id, job.id)
            return store.get_workflow(workflow.id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="workflow not found") from exc
        except WorkflowConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            store.mark_submission_failed(
                workflow_id,
                {"type": type(exc).__name__, "message": str(exc)},
            )
            raise HTTPException(status_code=502, detail="downstream retry submission failed") from exc

    @app.post(
        "/api/v1/internal/rca/jobs",
        response_model=RCAJob,
        status_code=status.HTTP_201_CREATED,
        dependencies=[store_auth],
        operation_id="create_internal_rca_job",
    )
    def create_internal_rca_job(
        request: RCAJobCreateRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> RCAJob:
        return store.create_rca_job(
            request.model_dump(mode="json"),
            idempotency_key or str(uuid4()),
        )

    @app.get(
        "/api/v1/internal/rca/jobs/{job_id}",
        response_model=RCAJob,
        dependencies=[store_auth],
        operation_id="get_internal_rca_job",
    )
    def get_internal_rca_job(job_id: UUID) -> RCAJob:
        job = store.get_rca_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="RCA job not found")
        return job

    @app.post(
        "/api/v1/internal/remediation/jobs",
        response_model=RemediationJob,
        status_code=status.HTTP_201_CREATED,
        dependencies=[store_auth],
        operation_id="create_internal_remediation_job",
    )
    def create_internal_remediation_job(
        request: RemediationJobCreateRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> RemediationJob:
        return store.create_remediation_job(
            request.model_dump(mode="json"),
            idempotency_key or str(uuid4()),
        )

    @app.get(
        "/api/v1/internal/remediation/jobs/{job_id}",
        response_model=RemediationJob,
        dependencies=[store_auth],
        operation_id="get_internal_remediation_job",
    )
    def get_internal_remediation_job(job_id: UUID) -> RemediationJob:
        job = store.get_remediation_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="remediation job not found")
        return job

    @app.post(
        "/api/v1/internal/learning/jobs",
        response_model=LearningJob,
        status_code=status.HTTP_201_CREATED,
        dependencies=[store_auth],
        operation_id="create_internal_learning_job",
    )
    def create_internal_learning_job(
        request: LearningJobCreateRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> LearningJob:
        return store.create_learning_job(
            request.model_dump(mode="json"), idempotency_key or str(uuid4())
        )

    @app.get(
        "/api/v1/internal/learning/jobs/{job_id}",
        response_model=LearningJob,
        dependencies=[store_auth],
        operation_id="get_internal_learning_job",
    )
    def get_internal_learning_job(job_id: UUID) -> LearningJob:
        job = store.get_learning_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="learning job not found")
        return job

    @app.post(
        "/api/v1/internal/execution/claim",
        dependencies=[store_auth],
        operation_id="claim_agent_execution",
    )
    def claim_execution(request: ExecutionClaimRequest):
        job = store.claim_execution(
            request.service,
            request.owner,
            request.lease_seconds,
            request.max_attempts,
        )
        if job is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        return JSONResponse(content=job.model_dump(mode="json"))

    @app.post(
        "/api/v1/internal/execution/renew",
        response_model=RenewResponse,
        dependencies=[store_auth],
        operation_id="renew_agent_execution",
    )
    def renew_execution(request: ExecutionRenewRequest) -> RenewResponse:
        return RenewResponse(
            renewed=store.renew_execution(
                request.service,
                request.job_id,
                request.owner,
                request.lease_seconds,
            )
        )

    @app.post(
        "/api/v1/internal/rca/jobs/{job_id}/finish",
        response_model=RCAJob,
        dependencies=[store_auth],
        operation_id="finish_internal_rca_job",
    )
    def finish_internal_rca_job(job_id: UUID, request: RCAFinishRequest) -> RCAJob:
        job = store.finish_rca_job(
            job_id,
            request.outcome,
            result=request.result,
            raw_output=request.raw_output,
            error=request.error,
            max_attempts=request.max_attempts,
        )
        if job is None:
            raise HTTPException(status_code=404, detail="RCA job not found")
        return job

    @app.post(
        "/api/v1/internal/remediation/jobs/{job_id}/finish",
        response_model=RemediationJob,
        dependencies=[store_auth],
        operation_id="finish_internal_remediation_job",
    )
    def finish_internal_remediation_job(
        job_id: UUID, request: RemediationFinishRequest
    ) -> RemediationJob:
        job = store.finish_remediation_job(
            job_id,
            request.status,
            result=request.result,
            raw_output=request.raw_output,
            error=request.error,
        )
        if job is None:
            raise HTTPException(status_code=404, detail="remediation job not found")
        return job

    @app.post(
        "/api/v1/internal/learning/jobs/{job_id}/finish",
        response_model=LearningJob,
        dependencies=[store_auth],
        operation_id="finish_internal_learning_job",
    )
    def finish_internal_learning_job(
        job_id: UUID, request: LearningFinishRequest
    ) -> LearningJob:
        job = store.finish_learning_job(
            job_id,
            request.outcome,
            result=(
                request.result.model_dump(mode="json")
                if request.result is not None
                else None
            ),
            raw_output=request.raw_output,
            error=request.error,
            max_attempts=request.max_attempts,
        )
        if job is None:
            raise HTTPException(status_code=404, detail="learning job not found")
        return job

    @app.post(
        "/api/v1/internal/rca/jobs/{job_id}/tool-calls",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[store_auth],
        operation_id="record_internal_rca_tool_call",
    )
    def record_internal_rca_tool_call(job_id: UUID, request: ToolCallRequest) -> None:
        store.record_tool_call(
            "rca", job_id, request.tool_name, request.arguments, request.result
        )

    @app.post(
        "/api/v1/internal/remediation/jobs/{job_id}/tool-calls",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[store_auth],
        operation_id="record_internal_remediation_tool_call",
    )
    def record_internal_remediation_tool_call(
        job_id: UUID, request: ToolCallRequest
    ) -> None:
        store.record_tool_call(
            "remediator", job_id, request.tool_name, request.arguments, request.result
        )

    @app.post(
        "/api/v1/internal/remediation/jobs/{job_id}/artifacts",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[store_auth],
        operation_id="upsert_internal_remediation_artifact",
    )
    def upsert_internal_remediation_artifact(
        job_id: UUID, request: ArtifactUpsertRequest
    ) -> None:
        store.upsert_artifact(job_id, request.filename, request.content)

    @app.get(
        "/api/v1/internal/remediation/jobs/{job_id}/artifacts",
        response_model=ArtifactListResponse,
        dependencies=[store_auth],
        operation_id="list_internal_remediation_artifacts",
    )
    def list_internal_remediation_artifacts(job_id: UUID) -> ArtifactListResponse:
        return ArtifactListResponse(filenames=store.list_artifacts(job_id))

    app.state.store = store
    app.state.coordinator = coordinator
    return app
