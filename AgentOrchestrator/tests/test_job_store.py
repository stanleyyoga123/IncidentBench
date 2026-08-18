from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from store import WorkflowStore


class Cursor:
    def __init__(self, rows=None, all_rows=None, rowcount=0):
        self.rows = iter(rows or [])
        self.all_rows = all_rows or []
        self.queries = []
        self.rowcount = rowcount

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=None):
        self.queries.append((" ".join(query.split()), params))

    def fetchone(self):
        return next(self.rows)

    def fetchall(self):
        return self.all_rows


class Connection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True


class Store(WorkflowStore):
    def __init__(self, connection, job=None):
        self._connection = connection
        self._job = job

    @contextmanager
    def connection(self):
        yield self._connection

    def get_rca_job(self, job_id):
        return self._job


def test_claim_reclaims_expired_remediation_as_needs_review():
    cursor = Cursor(
        rows=[
            {
                "holder_type": "remediation",
                "holder_job_id": "remediation-job",
                "lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
            },
            None,
        ]
    )
    connection = Connection(cursor)
    store = Store(connection)

    assert store.claim_execution("rca", "worker", lease_seconds=60, max_attempts=3) is None
    sql = "\n".join(query for query, _ in cursor.queries)
    assert "UPDATE remediation_job SET status='needs_review'" in sql
    assert "UPDATE agent_execution_slot SET holder_type=NULL" in sql
    assert connection.committed is True


def test_claim_requeues_or_fails_expired_rca_holder():
    cursor = Cursor(
        rows=[
            {
                "holder_type": "rca",
                "holder_job_id": "rca-job",
                "lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
            },
            None,
        ]
    )
    store = Store(Connection(cursor))

    assert store.claim_execution(
        "remediation", "worker", lease_seconds=60, max_attempts=3
    ) is None
    sql = "\n".join(query for query, _ in cursor.queries)
    assert "UPDATE rca_job SET status=CASE WHEN attempts < %s THEN 'queued' ELSE 'failed' END" in sql
    assert "UPDATE agent_execution_slot SET holder_type=NULL" in sql


def test_finish_rca_requeues_until_max_attempts():
    job = SimpleNamespace(attempts=2)
    cursor = Cursor()
    store = Store(Connection(cursor), job=job)

    store.finish_rca_job(uuid4(), "failed", error={"type": "Timeout"}, max_attempts=3)
    sql = "\n".join(query for query, _ in cursor.queries)
    assert "UPDATE rca_job SET status=%s" in sql
    assert cursor.queries[0][1][0] == "queued"
    assert "UPDATE agent_execution_slot SET holder_type=NULL" in sql


def test_finish_rca_fails_after_max_attempts():
    job = SimpleNamespace(attempts=3)
    cursor = Cursor()
    store = Store(Connection(cursor), job=job)

    store.finish_rca_job(uuid4(), "failed", error={"type": "Timeout"}, max_attempts=3)
    assert cursor.queries[0][1][0] == "failed"


def test_finish_remediation_accepts_needs_review_only_as_terminal():
    cursor = Cursor()
    store = Store(Connection(cursor))
    store.get_remediation_job = lambda _job_id: SimpleNamespace()

    store.finish_remediation_job(uuid4(), "needs_review", error={"type": "Ambiguous"})
    sql = "\n".join(query for query, _ in cursor.queries)
    assert "UPDATE remediation_job SET status=%s" in sql
    assert cursor.queries[0][1][0] == "needs_review"
    assert "completed_at=now()" in sql


def test_write_file_audit_persists_and_lists_artifact():
    job_id = uuid4()
    write_cursor = Cursor()
    connection = Connection(write_cursor)
    store = Store(connection)

    store.record_tool_call(
        "remediator",
        job_id,
        "remediator.write_file",
        {"filename": "remediation.yml", "content": "---\n- hosts: localhost\n"},
        {"ok": True},
    )

    sql = "\n".join(query for query, _ in write_cursor.queries)
    assert "INSERT INTO agent_tool_call" in sql
    assert "INSERT INTO remediation_artifact" in sql
    assert connection.committed is True

    list_cursor = Cursor(all_rows=[{"filename": "remediation.yml"}])
    store = Store(Connection(list_cursor))
    assert store.list_artifacts(job_id) == ["remediation.yml"]
