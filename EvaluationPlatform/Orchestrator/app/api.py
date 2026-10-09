from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from config import Settings, get_settings
from features.agent_workflow.agent_client import AgentClient
from features.agent_workflow.coordinator_loops import CoordinatorLoops
from features.agent_workflow.router import create_agent_router
from features.agent_workflow.workflow_coordinator import WorkflowCoordinator
from features.agent_workflow.workflow_store import WorkflowStore
from features.evaluation.evaluation_repository import EvaluationRepository
from features.evaluation.evaluation_service import EvaluationService
from features.evaluation.router import create_evaluation_router
from infrastructure.authentication import bearer
from infrastructure.database import Database
from infrastructure.maintenance_gate import MaintenanceGate
from infrastructure.workflow_conflict_error import WorkflowConflictError


def create_app(
    settings: Settings | None = None,
    *,
    start_loops: bool = True,
    store: WorkflowStore | None = None,
    rca: AgentClient | None = None,
    remediator: AgentClient | None = None,
    learning: AgentClient | None = None,
    database: Database | None = None,
    maintenance_gate: MaintenanceGate | None = None,
    evaluation_service: EvaluationService | None = None,
) -> FastAPI:
    settings = settings if settings is not None else get_settings()
    database = database if database is not None else Database(settings.database.dsn)
    store = store if store is not None else WorkflowStore(database)
    maintenance_gate = (
        maintenance_gate if maintenance_gate is not None else MaintenanceGate(database)
    )
    evaluation_service = (
        evaluation_service
        if evaluation_service is not None
        else EvaluationService(EvaluationRepository(database))
    )
    rca = rca if rca is not None else AgentClient(**settings.rca.model_dump())
    remediator = (
        remediator
        if remediator is not None
        else AgentClient(**settings.remediator.model_dump())
    )
    learning = (
        learning
        if learning is not None
        else AgentClient(**settings.learning.model_dump())
    )
    coordinator = WorkflowCoordinator(
        store,
        rca,
        remediator,
        learning,
        maintenance_gate,
        batch_size=settings.scheduler.batch_size,
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
        try:
            yield
        finally:
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

    @app.exception_handler(WorkflowConflictError)
    async def conflict_handler(_request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    app.include_router(
        create_evaluation_router(evaluation_service, bearer(settings.api.control_token))
    )
    app.include_router(
        create_agent_router(
            store,
            coordinator,
            maintenance_gate,
            bearer(settings.api.ingestion_token),
            bearer(settings.api.control_token),
            bearer(settings.api.store_token),
        )
    )

    @app.get("/health", operation_id="get_agent_orchestrator_health")
    def health() -> dict:
        return {
            "status": "ok",
            "active_execution_available": store.execution_available(),
        }

    app.state.store = store
    app.state.coordinator = coordinator
    return app
