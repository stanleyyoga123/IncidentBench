import secrets
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, status

from config import Settings, get_settings
from engine import LearningEngine
from schema import LearningJob, LearningJobRequest
from store import LearningJobStore
from worker import LearningWorker


def create_app(
    settings: Settings | None = None,
    *,
    start_worker: bool = True,
    store: LearningJobStore | None = None,
    engine: LearningEngine | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    store = store or LearningJobStore(**settings.orchestrator.model_dump())
    engine = engine or LearningEngine(settings)
    worker = LearningWorker(store, engine, settings)

    def authorize(authorization: str | None = Header(default=None)) -> None:
        supplied = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
        if not supplied or not secrets.compare_digest(supplied, settings.api.submit_token):
            raise HTTPException(status_code=401, detail="invalid bearer token")

    @asynccontextmanager
    async def lifespan(_app):
        if start_worker:
            worker.start()
        yield
        if start_worker:
            worker.stop()
        store.close()

    app = FastAPI(
        title="LearningAgent API",
        version="1.0.0",
        description="Durable generation of reusable lessons from completed workflows.",
        lifespan=lifespan,
    )
    auth = Depends(authorize)

    @app.get("/health", operation_id="get_learning_agent_health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post(
        "/api/v1/learning/jobs",
        response_model=LearningJob,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[auth],
        operation_id="create_learning_job",
    )
    def create_job(
        request: LearningJobRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> LearningJob:
        return store.create(request, idempotency_key or str(uuid4()))

    @app.get(
        "/api/v1/learning/jobs/{job_id}",
        response_model=LearningJob,
        dependencies=[auth],
        operation_id="get_learning_job",
    )
    def get_job(job_id: UUID) -> LearningJob:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="learning job not found")
        return job

    app.state.store = store
    app.state.worker = worker
    return app
