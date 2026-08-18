import secrets
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, status

from config import Settings, get_settings
from engine import RemediationEngine
from schema import RemediationJob, RemediationJobRequest
from store import RemediationJobStore
from worker import RemediatorWorker


def create_app(
    settings: Settings | None = None, *, start_worker=True,
    store: RemediationJobStore | None = None,
    engine: RemediationEngine | None = None,
):
    settings = settings or get_settings()
    store = store or RemediationJobStore(
        settings.orchestrator.base_url,
        settings.orchestrator.token,
        settings.orchestrator.timeout_seconds,
    )
    engine = engine or RemediationEngine(
        settings,
        audit_callback=lambda job_id, name, args, result: store.record_tool_call(
            job_id, name, args, result
        ),
    )
    worker = RemediatorWorker(store, engine, settings)

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

    app = FastAPI(title="RemediatorAgent API", version="1.0.0", lifespan=lifespan)
    auth = Depends(authorize)

    @app.get("/health", operation_id="get_remediator_agent_health")
    def health():
        return {"status": "ok"}

    @app.post(
        "/api/v1/remediation/jobs",
        response_model=RemediationJob,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[auth],
        operation_id="create_remediation_job",
    )
    def create_job(
        request: RemediationJobRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        return store.create(request, idempotency_key or str(uuid4()))

    @app.get(
        "/api/v1/remediation/jobs/{job_id}",
        response_model=RemediationJob,
        dependencies=[auth],
        operation_id="get_remediation_job",
    )
    def get_job(job_id: UUID):
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="remediation job not found")
        return job

    app.state.store = store
    app.state.worker = worker
    return app
