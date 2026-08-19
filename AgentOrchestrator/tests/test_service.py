from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx

from schema import DownstreamJob, Workflow
from service import AUTO_APPROVAL_ACTOR, AUTO_APPROVAL_REASON, WorkflowCoordinator
from store import WorkflowConflictError


def now():
    return datetime.now(timezone.utc)


def workflow(**overrides) -> Workflow:
    stamp = now()
    values = {
        "id": uuid4(),
        "status": "rca_running",
        "version": 2,
        "rca_job_id": uuid4(),
        "remediation_job_id": None,
        "created_at": stamp,
        "updated_at": stamp,
    }
    values.update(overrides)
    return Workflow.model_validate(values)


class MemoryStore:
    def __init__(self, items: list[Workflow]):
        self.workflows = {item.id: item for item in items}
        self.failed: dict[UUID, dict] = {}
        self.attached: dict[UUID, UUID] = {}

    def list_reconcilable(self):
        return [
            item
            for item in self.workflows.values()
            if item.status in {
                "rca_queued",
                "rca_running",
                "awaiting_approval",
                "remediation_queued",
                "remediation_running",
                "learning_submitting",
                "learning_queued",
                "learning_running",
            }
        ]

    def get_workflow(self, workflow_id, *, for_update=False, conn=None):
        return self.workflows.get(workflow_id)

    def set_rca_state(self, workflow_id, status, *, result=None, error=None):
        current = self.workflows[workflow_id]
        if status == "succeeded":
            required = (result or {}).get("remediation_required") is True
            next_status = "awaiting_approval" if required else "learning_submitting"
        else:
            next_status = "failed" if status in {"failed", "needs_review"} else "rca_running"
        self.workflows[workflow_id] = current.model_copy(
            update={"status": next_status, "version": current.version + 1, "error": error}
        )

    def decide(self, workflow_id, decision, actor, reason, expected_version):
        current = self.workflows[workflow_id]
        if current.status != "awaiting_approval":
            raise WorkflowConflictError(f"workflow is {current.status}, not awaiting_approval")
        if current.version != expected_version:
            raise WorkflowConflictError("stale workflow version")
        status = "remediation_submitting" if decision == "approved" else "closed_declined"
        updated = current.model_copy(
            update={
                "status": status,
                "decision": decision,
                "decision_actor": actor,
                "decision_reason": reason,
                "version": current.version + 1,
            }
        )
        self.workflows[workflow_id] = updated
        return updated

    def attach_remediation_job(self, workflow_id, job_id):
        current = self.workflows[workflow_id]
        self.attached[workflow_id] = job_id
        self.workflows[workflow_id] = current.model_copy(
            update={"status": "remediation_queued", "remediation_job_id": job_id}
        )

    def set_remediation_state(self, workflow_id, status, *, error=None):
        current = self.workflows[workflow_id]
        next_status = "learning_submitting" if status == "succeeded" else status
        self.workflows[workflow_id] = current.model_copy(
            update={"status": next_status, "version": current.version + 1, "error": error}
        )

    def anomaly_payloads(self, _workflow_id):
        return [{"event_id": "a" * 64, "resource": "deployments", "name": "checkout", "metric": "latency"}]

    def tool_calls_for_workflow(self, _workflow):
        return []

    def attach_learning_job(self, workflow_id, job_id):
        current = self.workflows[workflow_id]
        self.workflows[workflow_id] = current.model_copy(
            update={
                "status": "learning_queued", "learning_job_id": job_id,
                "learning_status": "queued",
            }
        )

    def set_learning_state(self, workflow_id, status, *, error=None):
        current = self.workflows[workflow_id]
        final = "completed_remediated" if current.remediation_job_id else "completed_no_action"
        self.workflows[workflow_id] = current.model_copy(
            update={"status": final, "learning_status": status, "learning_error": error}
        )

    def mark_submission_failed(self, workflow_id, error):
        current = self.workflows[workflow_id]
        self.failed[workflow_id] = error
        self.workflows[workflow_id] = current.model_copy(
            update={"status": "failed", "error": error}
        )


class FakeRca:
    def __init__(self, jobs: dict[UUID, DownstreamJob]):
        self.jobs = jobs

    def get_rca(self, job_id):
        return self.jobs[job_id]


class FakeRemediator:
    def __init__(self, fail: Exception | None = None):
        self.fail = fail
        self.created = []
        self.jobs = {}

    def create_remediation(self, workflow_id, rca_job, approval, attempt=1):
        if self.fail is not None:
            raise self.fail
        job = DownstreamJob(id=uuid4(), status="queued")
        self.created.append(
            {
                "workflow_id": workflow_id,
                "rca_job": rca_job,
                "approval": approval,
                "job": job,
            }
        )
        self.jobs[job.id] = job
        return job

    def get_remediation(self, job_id):
        return self.jobs[job_id]


class FakeLearning:
    def __init__(self):
        self.created = []
        self.jobs = {}

    def create_learning(self, workflow_id, source, attempt=1):
        job = DownstreamJob(id=uuid4(), status="queued")
        self.created.append({"workflow_id": workflow_id, "source": source, "job": job})
        self.jobs[job.id] = job
        return job

    def get_learning(self, job_id):
        return self.jobs[job_id]


def coordinator(store, rca, remediator, learning=None):
    return WorkflowCoordinator(
        store, rca, remediator, learning or FakeLearning(), batch_size=100
    )


def test_rca_success_with_remediation_required_submits_remediator():
    rca_job_id = uuid4()
    item = workflow(rca_job_id=rca_job_id, status="rca_running", version=2)
    store = MemoryStore([item])
    rca = FakeRca(
        {
            rca_job_id: DownstreamJob(
                id=rca_job_id,
                status="succeeded",
                result={"remediation_required": True, "summary": "active incident"},
            )
        }
    )
    remediator = FakeRemediator()

    assert coordinator(store, rca, remediator).reconcile_once() == 1

    updated = store.get_workflow(item.id)
    assert updated.status == "remediation_queued"
    assert updated.decision == "approved"
    assert updated.decision_actor == AUTO_APPROVAL_ACTOR
    assert updated.decision_reason == AUTO_APPROVAL_REASON
    assert updated.remediation_job_id == remediator.created[0]["job"].id
    assert remediator.created[0]["approval"]["actor"] == AUTO_APPROVAL_ACTOR


def test_rca_success_without_remediation_does_not_submit():
    rca_job_id = uuid4()
    item = workflow(rca_job_id=rca_job_id, status="rca_running")
    store = MemoryStore([item])
    rca = FakeRca(
        {
            rca_job_id: DownstreamJob(
                id=rca_job_id,
                status="succeeded",
                result={"remediation_required": False, "summary": "recovered"},
            )
        }
    )
    remediator = FakeRemediator()
    learning = FakeLearning()

    assert coordinator(store, rca, remediator, learning).reconcile_once() == 1
    assert store.get_workflow(item.id).status == "learning_queued"
    assert remediator.created == []
    assert learning.created[0]["source"]["completion_type"] == "no_action"


def test_failed_learning_finalizes_without_lessons():
    learning_job_id = uuid4()
    item = workflow(
        status="learning_running",
        learning_job_id=learning_job_id,
        learning_status="running",
    )
    store = MemoryStore([item])
    rca = FakeRca({item.rca_job_id: DownstreamJob(id=item.rca_job_id, status="succeeded")})
    learning = FakeLearning()
    learning.jobs[learning_job_id] = DownstreamJob(
        id=learning_job_id,
        status="failed",
        error={"type": "InvalidOutput"},
    )

    assert coordinator(store, rca, FakeRemediator(), learning).reconcile_once() == 1
    updated = store.get_workflow(item.id)
    assert updated.status == "completed_no_action"
    assert updated.learning_status == "failed"


def test_successful_remediation_submits_learning_with_remediation_snapshot():
    remediation_job_id = uuid4()
    item = workflow(
        status="remediation_running",
        remediation_job_id=remediation_job_id,
    )
    store = MemoryStore([item])
    rca = FakeRca(
        {item.rca_job_id: DownstreamJob(id=item.rca_job_id, status="succeeded")}
    )
    remediator = FakeRemediator()
    remediator.jobs[remediation_job_id] = DownstreamJob(
        id=remediation_job_id,
        status="succeeded",
        result={"verification": "healthy"},
    )
    learning = FakeLearning()

    assert coordinator(store, rca, remediator, learning).reconcile_once() == 1
    assert store.get_workflow(item.id).status == "learning_queued"
    source = learning.created[0]["source"]
    assert source["completion_type"] == "remediated"
    assert source["remediation"]["result"] == {"verification": "healthy"}


def test_learning_tool_audits_are_count_and_size_bounded():
    calls = [
        {
            "id": index,
            "tool_name": "prometheus.query",
            "arguments": {"query": "x" * 8_000},
            "result": {"series": "y" * 8_000},
        }
        for index in range(120)
    ]

    bounded = WorkflowCoordinator._bounded_tool_calls(calls)

    assert len(bounded) == 100
    assert all(len(str(item)) < 4_000 for item in bounded)
    assert all(item.get("truncated") is True for item in bounded)


def test_existing_awaiting_approval_is_auto_submitted():
    rca_job_id = uuid4()
    item = workflow(
        rca_job_id=rca_job_id, status="awaiting_approval", version=4
    )
    store = MemoryStore([item])
    rca = FakeRca(
        {
            rca_job_id: DownstreamJob(
                id=rca_job_id,
                status="succeeded",
                result={"remediation_required": True},
            )
        }
    )
    remediator = FakeRemediator()

    assert coordinator(store, rca, remediator).reconcile_once() == 1
    updated = store.get_workflow(item.id)
    assert updated.status == "remediation_queued"
    assert updated.decision_actor == AUTO_APPROVAL_ACTOR
    assert len(remediator.created) == 1


def test_remediator_submit_error_marks_workflow_failed():
    rca_job_id = uuid4()
    item = workflow(rca_job_id=rca_job_id, status="awaiting_approval", version=3)
    store = MemoryStore([item])
    rca = FakeRca(
        {
            rca_job_id: DownstreamJob(
                id=rca_job_id,
                status="succeeded",
                result={"remediation_required": True},
            )
        }
    )
    remediator = FakeRemediator(
        fail=httpx.HTTPStatusError(
            "failed",
            request=httpx.Request("POST", "http://remediator/api/v1/remediation/jobs"),
            response=httpx.Response(500),
        )
    )

    coordinator(store, rca, remediator).reconcile_once()
    updated = store.get_workflow(item.id)
    assert updated.status == "failed"
    assert item.id in store.failed
    assert remediator.created == []
