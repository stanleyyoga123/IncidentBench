"""Evaluation controls. All SQL executes inside Orchestrator."""
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from store import WorkflowConflictError

LOCK = 920260913


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")


class EvaluationStore:
    def __init__(self, store):
        self.store = store

    @contextmanager
    def running(self):
        # Nonblocking acquisition prevents nested HTTP submissions deadlocking
        # behind a maintenance writer waiting for an outer dispatch to finish.
        with self.store.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock_shared(%s) AS locked", (LOCK,))
            if not cur.fetchone()["locked"]:
                raise WorkflowConflictError("evaluation transition in progress")
            cur.execute("SELECT maintenance FROM evaluation_control WHERE id=1")
            if cur.fetchone()["maintenance"]:
                raise WorkflowConflictError("evaluation maintenance is active")
            yield

    def state(self):
        with self.store.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM evaluation_control WHERE id=1")
            return cur.fetchone()

    def command(self, action, run_id):
        with self.store.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            cur.execute("SELECT * FROM evaluation_control WHERE id=1 FOR UPDATE")
            state = cur.fetchone()
            if action == "acquire":
                if state["run_id"] not in (None, run_id):
                    raise WorkflowConflictError("another evaluation owns this deployment")
                if state["run_id"] is None:
                    cur.execute("UPDATE evaluation_control SET run_id=%s, maintenance=true, reset_done=false WHERE id=1", (run_id,))
            else:
                if state["run_id"] != run_id:
                    raise WorkflowConflictError("evaluation run does not own this deployment")
                if action == "pause":
                    cur.execute("UPDATE evaluation_control SET maintenance=true WHERE id=1")
                elif action == "resume":
                    cur.execute("UPDATE evaluation_control SET maintenance=false WHERE id=1")
                elif action == "reset":
                    if not state["maintenance"]:
                        raise WorkflowConflictError("reset requires maintenance and stopped workers")
                    if not state["reset_done"]:
                        cur.execute("TRUNCATE incident_lesson, learning_job, agent_tool_call, remediation_artifact, remediation_job, rca_job, anomaly_event, agent_workflow RESTART IDENTITY")
                        cur.execute("DELETE FROM agent_execution_slot")
                        cur.execute("INSERT INTO agent_execution_slot (id) VALUES (1)")
                        cur.execute("UPDATE evaluation_control SET reset_done=true WHERE id=1")
                elif action == "release":
                    if not state["maintenance"]:
                        raise WorkflowConflictError("release requires maintenance")
                    cur.execute("UPDATE evaluation_control SET run_id=NULL WHERE id=1")
                else:
                    raise ValueError("unknown evaluation action")
            cur.execute("SELECT * FROM evaluation_control WHERE id=1")
            return cur.fetchone()

    def export(self, run_id):
        with self.store.connection() as conn, conn.cursor() as cur:
            # Acquire a session lock before starting the snapshot. Taking a
            # transaction lock inside repeatable-read could capture pre-reset
            # state while waiting for a reset writer. This dedicated connection
            # closes (and releases the session lock) on success or failure.
            cur.execute("SELECT pg_advisory_lock_shared(%s)", (LOCK,))
            conn.commit()
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cur.execute("SELECT * FROM evaluation_control WHERE id=1")
            state = cur.fetchone()
            if state["run_id"] != run_id or not state["maintenance"]:
                raise WorkflowConflictError("export requires owning run in maintenance")
            result = {"schema_version": 1, "run_id": run_id, "sessions": {}}
            for path in sorted((Path(__file__).parent / "evaluation_queries").glob("*.sql")):
                cur.execute(path.read_text())
                result["sessions"][path.stem] = next(iter(cur.fetchone().values()))
            return result


def register_evaluation_api(app, evaluation, control_auth):
    @app.get("/api/v1/evaluation", dependencies=[control_auth], operation_id="get_evaluation_state")
    def state():
        return evaluation.state()

    def endpoint(action):
        def command(request: EvaluationRequest):
            return evaluation.command(action, request.run_id)
        return command

    for action in ("acquire", "pause", "resume", "reset", "release"):
        app.post("/api/v1/evaluation/" + action, dependencies=[control_auth],
                 operation_id="evaluation_" + action)(endpoint(action))

    @app.get("/api/v1/evaluation/export", dependencies=[control_auth], operation_id="export_evaluation_sessions")
    def export(run_id: str):
        return evaluation.export(run_id)
