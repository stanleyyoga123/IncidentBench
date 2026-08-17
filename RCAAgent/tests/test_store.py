from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from store import RCAJobStore


class Cursor:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, _params=None):
        self.queries.append(" ".join(query.split()))

    def fetchone(self):
        return next(self.rows)


class Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass


class Store(RCAJobStore):
    def __init__(self, connection):
        self._connection = connection

    @contextmanager
    def connection(self):
        yield self._connection


def test_claim_marks_expired_remediation_as_needs_review():
    cursor = Cursor(
        [
            {
                "holder_type": "remediation",
                "holder_job_id": "remediation-job",
                "lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
            },
            None,
        ]
    )
    store = Store(Connection(cursor))

    assert store.claim("worker", lease_seconds=60, max_attempts=3) is None
    sql = "\n".join(cursor.queries)
    assert "UPDATE remediation_job SET status='needs_review'" in sql
    assert "UPDATE agent_execution_slot SET holder_type=NULL" in sql
