from fastapi import FastAPI
from fastapi.responses import JSONResponse

from config import Settings, get_settings
from features.agent_workflow.orchestration_router import create_orchestration_router
from features.agent_workflow.router import create_agent_router
from features.agent_workflow.workflow_store import WorkflowStore
from features.evaluation.evaluation_repository import EvaluationRepository
from features.evaluation.evaluation_service import EvaluationService
from features.evaluation.router import create_evaluation_router
from infrastructure.authentication import bearer
from infrastructure.database import Database
from infrastructure.maintenance_gate import MaintenanceGate
from infrastructure.workflow_conflict_error import WorkflowConflictError


def create_app(
    settings: Settings | None = None, *, store: WorkflowStore | None = None,
    database: Database | None = None, maintenance_gate: MaintenanceGate | None = None,
    evaluation_service: EvaluationService | None = None,
) -> FastAPI:
    settings = settings if settings is not None else get_settings()
    database = database if database is not None else Database(settings.database.dsn)
    store = store if store is not None else WorkflowStore(database)
    maintenance_gate = maintenance_gate if maintenance_gate is not None else MaintenanceGate(database)
    evaluation_service = evaluation_service if evaluation_service is not None else EvaluationService(EvaluationRepository(database))
    app = FastAPI(title="EvaluationPlatform Orchestrator API", version="1.0.0",
                  description="Evaluation controls, durable submissions and artifact export.")

    @app.exception_handler(WorkflowConflictError)
    async def conflict_handler(_request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(KeyError)
    async def missing_handler(_request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    control = bearer(settings.api.control_token)
    store_auth = bearer(settings.api.store_token)
    app.include_router(create_evaluation_router(evaluation_service, control))
    app.include_router(create_agent_router(store, maintenance_gate, control, store_auth))
    app.include_router(create_orchestration_router(store, maintenance_gate, store_auth))

    @app.get("/health", operation_id="get_evaluation_orchestrator_health")
    def health() -> dict:
        return {"status": "ok", "active_execution_available": store.execution_available()}

    app.state.store = store
    return app
