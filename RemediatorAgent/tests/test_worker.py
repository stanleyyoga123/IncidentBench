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

    def needs_review(self, job_id, exc):
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


def test_worker_marks_engine_failure_for_review():
    store = Store(job_request())

    assert worker(store, FailingEngine()).run_once() is True
    assert store.succeeded is None
    assert isinstance(store.reviewed[1], RuntimeError)
