import secrets
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, status

from config import Settings, get_settings
from engine import RCAEngine
from schema import RCAJob, RCAJobRequest
from store import RCAJobStore
from worker import RCAWorker


def create_app(
    settings: Settings | None = None, *, start_worker: bool = True,
    store: RCAJobStore | None = None, engine: RCAEngine | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    store = store or RCAJobStore(settings.database.dsn)
    engine = engine or RCAEngine(
        settings,
        audit_callback=lambda job_id, name, args, result: store.record_tool_call(
            job_id, name, args, result
        ),
    )
    worker = RCAWorker(store, engine, settings)

    def authorize(authorization: str | None = Header(default=None)):
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

    app = FastAPI(title="RCAAgent API", version="1.0.0", lifespan=lifespan)
    auth = Depends(authorize)

    @app.get("/health", operation_id="get_rca_agent_health")
    def health():
        return {"status": "ok"}

    @app.post(
        "/api/v1/rca/jobs",
        response_model=RCAJob,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[auth],
        operation_id="create_rca_job",
    )
    def create_job(
        request: RCAJobRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        return store.create(request, idempotency_key or str(uuid4()))

    @app.get(
        "/api/v1/rca/jobs/{job_id}",
        response_model=RCAJob,
        dependencies=[auth],
        operation_id="get_rca_job",
    )
    def get_job(job_id: UUID):
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="RCA job not found")
        return job

    app.state.store = store
    app.state.worker = worker
    return app
