import secrets
from contextlib import asynccontextmanager
from typing import Callable
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, status

from clients import AgentClient
from config import Settings, get_settings
from schema import (
    AnomalyBatchRequest,
    DecisionRequest,
    IngestionResponse,
    RetryRequest,
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
) -> FastAPI:
    settings = settings or get_settings()
    store = store or WorkflowStore(settings.database.dsn)
    rca = rca or AgentClient(**settings.rca.model_dump())
    remediator = remediator or AgentClient(**settings.remediator.model_dump())
    coordinator = WorkflowCoordinator(
        store, rca, remediator, batch_size=settings.scheduler.batch_size
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

    app = FastAPI(
        title="AgentOrchestrator API",
        version="1.0.0",
        description="Durable anomaly ingestion and RCA/remediation coordination.",
        lifespan=lifespan,
    )
    ingest_auth = Depends(_bearer(settings.api.ingestion_token))
    control_auth = Depends(_bearer(settings.api.control_token))

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

    def decision(workflow_id: UUID, request: DecisionRequest, value: str) -> Workflow:
        try:
            workflow = store.decide(
                workflow_id, value, request.actor, request.reason, request.expected_version
            )
            if value == "approved":
                rca_job = rca.get_rca(workflow.rca_job_id)
                job = remediator.create_remediation(
                    workflow.id,
                    rca_job,
                    {"actor": request.actor, "reason": request.reason,
                     "workflow_version": workflow.version},
                )
                store.attach_remediation_job(workflow.id, job.id)
                return store.get_workflow(workflow.id)
            return workflow
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="workflow not found") from exc
        except WorkflowConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
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

    app.state.store = store
    app.state.coordinator = coordinator
    return app
