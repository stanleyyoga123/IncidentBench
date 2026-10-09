from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from psycopg import Cursor

from infrastructure.database import Database
from infrastructure.maintenance_gate import LOCK


class EvaluationRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def state(self) -> dict[str, Any]:
        with self._database.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM evaluation_control WHERE id=1")
            return cur.fetchone()

    @contextmanager
    def transition(self) -> Iterator[tuple[Cursor, dict[str, Any]]]:
        with self._database.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            cur.execute("SELECT * FROM evaluation_control WHERE id=1 FOR UPDATE")
            yield cur, cur.fetchone()

    def acquire(self, cur: Cursor, run_id: str) -> None:
        cur.execute(
            "UPDATE evaluation_control SET run_id=%s, maintenance=true, reset_done=false WHERE id=1",
            (run_id,),
        )

    def pause(self, cur: Cursor) -> None:
        cur.execute("UPDATE evaluation_control SET maintenance=true WHERE id=1")

    def resume(self, cur: Cursor) -> None:
        cur.execute("UPDATE evaluation_control SET maintenance=false WHERE id=1")

    def reset(self, cur: Cursor) -> None:
        cur.execute(
            "TRUNCATE incident_lesson, learning_job, agent_tool_call, remediation_artifact, remediation_job, rca_job, anomaly_event, agent_workflow RESTART IDENTITY"
        )
        cur.execute("DELETE FROM agent_execution_slot")
        cur.execute("INSERT INTO agent_execution_slot (id) VALUES (1)")
        cur.execute("UPDATE evaluation_control SET reset_done=true WHERE id=1")

    def release(self, cur: Cursor) -> None:
        cur.execute("UPDATE evaluation_control SET run_id=NULL WHERE id=1")

    def transition_state(self, cur: Cursor) -> dict[str, Any]:
        cur.execute("SELECT * FROM evaluation_control WHERE id=1")
        return cur.fetchone()

    @contextmanager
    def export_snapshot(self) -> Iterator[tuple[Cursor, dict[str, Any]]]:
        with self._database.connection() as conn, conn.cursor() as cur:
            # Acquire a session lock before starting the snapshot. Taking a
            # transaction lock inside repeatable-read could capture pre-reset
            # state while waiting for a reset writer. This dedicated connection
            # closes (and releases the session lock) on success or failure.
            cur.execute("SELECT pg_advisory_lock_shared(%s)", (LOCK,))
            conn.commit()
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cur.execute("SELECT * FROM evaluation_control WHERE id=1")
            yield cur, cur.fetchone()

    def export_sessions(self, cur: Cursor) -> dict[str, Any]:
        sessions: dict[str, Any] = {}
        for path in sorted((Path(__file__).parent / "queries").glob("*.sql")):
            cur.execute(path.read_text())
            sessions[path.stem] = next(iter(cur.fetchone().values()))
        return sessions
