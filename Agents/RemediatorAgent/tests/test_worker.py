import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

from schema import RemediationResult
from worker import RemediatorWorker


class Store:
    def __init__(self, request):
        self.job = SimpleNamespace(id=uuid4(), request=request)
        self.succeeded = None
        self.reviewed = None

    def claim(self, _owner, _lease_seconds):
        return self.job

    def list_artifacts(self, _job_id):
        return ["inventory.ini", "remediation.yml"]

    def succeed(self, job_id, result, raw):
        self.succeeded = (job_id, result, raw)

    def fail(self, job_id, exc, **output):
        self.reviewed = (job_id, exc)

    def renew(self, *_args):
        return True


class Engine:
    def run(self, _job_id, _request):
        return RemediationResult(summary="complete"), "raw"


class FailingEngine:
    def run(self, _job_id, _request):
        raise RuntimeError("ambiguous execution")


def job_request():
    rca_result = {"remediation_required": True}
    canonical = json.dumps(rca_result, sort_keys=True, separators=(",", ":"))
    return {
        "rca_job_id": str(uuid4()),
        "rca_result": rca_result,
        "rca_result_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "approval": {
            "actor": "operator",
            "reason": "evidence reviewed",
            "workflow_version": 1,
        },
    }


def worker(store, engine):
    settings = SimpleNamespace(
        worker=SimpleNamespace(lease_seconds=60, poll_interval_seconds=1)
    )
    return RemediatorWorker(store, engine, settings)


def test_worker_adds_persisted_artifact_names_to_result():
    store = Store(job_request())

    assert worker(store, Engine()).run_once() is True
    _, result, raw = store.succeeded
    assert result.artifacts == ["inventory.ini", "remediation.yml"]
    assert raw == "raw"
    assert store.reviewed is None


def test_worker_marks_exception_without_output_failed():
    store = Store(job_request())

    assert worker(store, FailingEngine()).run_once() is True
    assert store.succeeded is None
    assert isinstance(store.reviewed[1], RuntimeError)


def test_worker_completes_unverified_agent_output(monkeypatch):
    import engine as module
    raw = "Status\n- Automation: not executed\n- Recovery: unverified"
    monkeypatch.setattr(module.TOOL_REGISTRY, "describe_openai_format", lambda tools: [])
    monkeypatch.setattr(module, "Agent", lambda **kwargs: SimpleNamespace(run=lambda prompt: raw))
    settings = SimpleNamespace(client=SimpleNamespace(model="test", url="http://test", token="test", timeout_seconds=1),
                               manager=SimpleNamespace(max_rounds=1))
    store = Store(job_request())
    saved = []
    store.record_output = lambda *args: saved.append(args)
    assert worker(store, module.RemediationEngine(settings)).run_once()
    assert store.reviewed is None
    assert store.succeeded[2] == raw
    assert "Recovery: unverified" in store.succeeded[1].summary
    assert len(saved) == 2


def test_checkpoint_http_failure_retries_output_in_failure_finish():
    class CheckpointFailure:
        def run(self, job_id, request):
            self.last_raw_output = 'generated before network failure'
            self.output_callback(job_id, self.last_raw_output)
    store = Store(job_request())
    def unavailable(*args):
        raise RuntimeError('checkpoint temporarily unavailable')
    store.record_output = unavailable
    failed = []
    store.fail = lambda job_id, exc, **output: failed.append(output)
    assert worker(store, CheckpointFailure()).run_once()
    assert failed[0]['raw_output'] == 'generated before network failure'


def test_rejected_checkpoint_cannot_overwrite_new_owner_in_failure_finish():
    import httpx
    class LostLease:
        def run(self, job_id, request):
            self.last_raw_output = 'stale answer'
            self.output_callback(job_id, self.last_raw_output)
    store = Store(job_request())
    def rejected(*args):
        request = httpx.Request('POST', 'http://orchestrator/jobs/output')
        raise httpx.HTTPStatusError('lease lost', request=request, response=httpx.Response(409, request=request))
    store.record_output = rejected
    assert worker(store, LostLease()).run_once()
    assert store.reviewed is None and store.succeeded is None
