from contextlib import contextmanager
from typing import Iterator

from infrastructure.database import Database
from infrastructure.workflow_conflict_error import WorkflowConflictError

LOCK = 920260913


class MaintenanceGate:
    def __init__(self, database: Database) -> None:
        self._database = database

    @contextmanager
    def running(self) -> Iterator[None]:
        # Nonblocking acquisition prevents nested HTTP submissions deadlocking
        # behind a maintenance writer waiting for an outer dispatch to finish.
        with self._database.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT pg_try_advisory_xact_lock_shared(%s) AS locked", (LOCK,)
            )
            if not cur.fetchone()["locked"]:
                raise WorkflowConflictError("evaluation transition in progress")
            cur.execute("SELECT maintenance FROM evaluation_control WHERE id=1")
            if cur.fetchone()["maintenance"]:
                raise WorkflowConflictError("evaluation maintenance is active")
            yield
