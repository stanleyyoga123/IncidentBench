from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from store import RemediationJobStore


class Cursor:
    def __init__(self, rows=None, all_rows=None):
        self.rows = iter(rows or [])
        self.all_rows = all_rows or []
        self.queries = []

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


class Store(RemediationJobStore):
    def __init__(self, connection):
        self._connection = connection

    @contextmanager
    def connection(self):
        yield self._connection


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

    assert store.claim("worker", lease_seconds=60) is None
    sql = "\n".join(query for query, _ in cursor.queries)
    assert "UPDATE rca_job SET status=CASE WHEN attempts < 3" in sql
    assert "UPDATE agent_execution_slot SET holder_type=NULL" in sql


def test_write_file_audit_persists_and_lists_artifact():
    job_id = uuid4()
    write_cursor = Cursor()
    connection = Connection(write_cursor)
    store = Store(connection)

    store.record_tool_call(
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
