from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from worker import LearningWorker


class Store:
    def __init__(self, job):
        self.job = job
        self.failed = []

    def claim(self, *_args):
        job, self.job = self.job, None
        return job

    def fail(self, job_id, exc, max_attempts, **output):
        self.failed.append((job_id, type(exc).__name__, max_attempts))


def test_worker_reports_invalid_model_output_for_retry():
    job = SimpleNamespace(
        id=uuid4(),
        request={
            "workflow_id": str(uuid4()),
            "source": {"completion_type": "no_action"},
            "source_sha256": "0" * 64,
        },
    )
    store = Store(job)
    engine = SimpleNamespace(run=lambda *_args: (_ for _ in ()).throw(ValueError("bad")))
    settings = SimpleNamespace(
        worker=SimpleNamespace(lease_seconds=60, max_attempts=3, poll_interval_seconds=2)
    )
    worker = LearningWorker(store, engine, settings)
    worker._heartbeat = lambda *_args: None
    assert worker.run_once() is True
    assert store.failed[0][2] == 3
