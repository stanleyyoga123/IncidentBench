from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from schema import AnomalyEventInput, Workflow


class WorkflowConflictError(RuntimeError):
    pass


class WorkflowStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        with Connection.connect(self._dsn, row_factory=dict_row) as conn:
            yield conn

    def ingest(self, anomalies: list[AnomalyEventInput]) -> tuple[int, int, list[dict[str, Any]]]:
        accepted = 0
        records = []
        with self.connection() as conn, conn.cursor() as cur:
            for anomaly in anomalies:
                payload = anomaly.model_dump(mode="json")
                cur.execute(
                    """
                    INSERT INTO anomaly_event (
                        id, event_id, detected_at, resource, name, metric, method,
                        detail, profile_id, profile_version, profile_parameters,
                        payload, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                    ON CONFLICT (event_id) DO NOTHING
                    RETURNING id
                    """,
                    (
                        uuid4(), anomaly.event_id, anomaly.detected_at,
                        anomaly.resource, anomaly.name, anomaly.metric,
                        anomaly.method, anomaly.detail, anomaly.profile_id,
                        anomaly.profile_version, Jsonb(anomaly.profile_parameters),
                        Jsonb(payload),
                    ),
                )
                row = cur.fetchone()
                duplicate = row is None
                if duplicate:
                    cur.execute(
                        "SELECT id FROM anomaly_event WHERE event_id=%s",
                        (anomaly.event_id,),
                    )
                    row = cur.fetchone()
                else:
                    accepted += 1
                records.append(
                    {"id": row["id"], "event_id": anomaly.event_id, "duplicate": duplicate}
                )
            conn.commit()
        return accepted, len(anomalies) - accepted, records

    def execution_available(self) -> bool:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT holder_job_id
                FROM agent_execution_slot
                WHERE id = 1
                  AND holder_job_id IS NOT NULL
                  AND lease_expires_at > now()
                """
            )
            return cur.fetchone() is None

    def claim_pending(self, limit: int) -> tuple[Workflow, list[dict[str, Any]]] | None:
        workflow_id = uuid4()
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock(920260817)")
            if not cur.fetchone()["pg_try_advisory_xact_lock"]:
                return None
            cur.execute(
                """
                SELECT id, payload FROM anomaly_event
                WHERE status = 'pending'
                ORDER BY detected_at, created_at
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (limit,),
            )
            rows = cur.fetchall()
            if not rows:
                return None
            cur.execute(
                """
                INSERT INTO agent_workflow (id, status)
                VALUES (%s, 'rca_submitting')
                RETURNING *
                """,
                (workflow_id,),
            )
            workflow = Workflow.model_validate(cur.fetchone())
            ids = [row["id"] for row in rows]
            cur.execute(
                """
                UPDATE anomaly_event
                SET status = 'rca_queued', workflow_id = %s, updated_at = now()
                WHERE id = ANY(%s)
                """,
                (workflow_id, ids),
            )
            conn.commit()
        return workflow, [row["payload"] for row in rows]

    def attach_rca_job(self, workflow_id: UUID, job_id: UUID) -> None:
        self._update_workflow(
            workflow_id,
            status="rca_queued",
            rca_job_id=job_id,
            error=None,
        )

    def list_reconcilable(self) -> list[Workflow]:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM agent_workflow
                WHERE status IN ('rca_queued', 'rca_running',
                                 'remediation_queued', 'remediation_running')
                ORDER BY created_at
                """
            )
            return [Workflow.model_validate(row) for row in cur.fetchall()]

    def anomaly_payloads(self, workflow_id: UUID) -> list[dict[str, Any]]:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM anomaly_event WHERE workflow_id=%s ORDER BY detected_at",
                (workflow_id,),
            )
            return [row["payload"] for row in cur.fetchall()]

    def list_workflows(self) -> list[Workflow]:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM agent_workflow ORDER BY created_at DESC")
            return [Workflow.model_validate(row) for row in cur.fetchall()]

    def get_workflow(self, workflow_id: UUID, *, for_update=False, conn=None) -> Workflow | None:
        owns_connection = conn is None
        if owns_connection:
            conn = Connection.connect(self._dsn, row_factory=dict_row)
        try:
            with conn.cursor() as cur:
                suffix = " FOR UPDATE" if for_update else ""
                cur.execute(f"SELECT * FROM agent_workflow WHERE id = %s{suffix}", (workflow_id,))
                row = cur.fetchone()
                return Workflow.model_validate(row) if row else None
        finally:
            if owns_connection:
                conn.close()

    def set_rca_state(self, workflow_id: UUID, status: str, *, result=None, error=None) -> None:
        if status == "succeeded":
            remediation_required = bool((result or {}).get("remediation_required"))
            workflow_status = "awaiting_approval" if remediation_required else "completed_no_action"
            self._update_workflow(
                workflow_id,
                status=workflow_status,
                error=None,
                completed=not remediation_required,
                anomaly_status=workflow_status,
            )
            return
        self._update_workflow(
            workflow_id,
            status="failed" if status in {"failed", "needs_review"} else "rca_running",
            error=error,
            anomaly_status="failed" if status in {"failed", "needs_review"} else "rca_running",
        )

    def decide(self, workflow_id: UUID, decision: str, actor: str, reason: str, expected_version: int) -> Workflow:
        with self.connection() as conn:
            current = self.get_workflow(workflow_id, for_update=True, conn=conn)
            if current is None:
                raise KeyError(workflow_id)
            if current.status != "awaiting_approval":
                raise WorkflowConflictError(f"workflow is {current.status}, not awaiting_approval")
            if current.version != expected_version:
                raise WorkflowConflictError(
                    f"expected version {expected_version}, active version is {current.version}"
                )
            status = "remediation_submitting" if decision == "approved" else "closed_declined"
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_workflow
                    SET status=%s, decision=%s, decision_actor=%s,
                        decision_reason=%s, version=version+1, updated_at=now(),
                        completed_at=CASE WHEN %s='declined' THEN now() ELSE completed_at END
                    WHERE id=%s RETURNING *
                    """,
                    (status, decision, actor, reason, decision, workflow_id),
                )
                row = cur.fetchone()
                cur.execute(
                    "UPDATE anomaly_event SET status=%s, updated_at=now() WHERE workflow_id=%s",
                    (status, workflow_id),
                )
            conn.commit()
            return Workflow.model_validate(row)

    def attach_remediation_job(self, workflow_id: UUID, job_id: UUID) -> None:
        self._update_workflow(
            workflow_id,
            status="remediation_queued",
            remediation_job_id=job_id,
            error=None,
            anomaly_status="remediation_queued",
        )

    def set_remediation_state(self, workflow_id: UUID, status: str, *, error=None) -> None:
        if status == "succeeded":
            self._update_workflow(
                workflow_id,
                status="completed_remediated",
                error=None,
                completed=True,
                anomaly_status="completed_remediated",
            )
        elif status in {"failed", "needs_review"}:
            self._update_workflow(
                workflow_id,
                status="needs_review" if status == "needs_review" else "failed",
                error=error,
                anomaly_status=status,
            )
        else:
            self._update_workflow(
                workflow_id,
                status="remediation_running",
                anomaly_status="remediation_running",
            )

    def fail_submission(self, workflow_id: UUID, error: dict[str, Any]) -> None:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE anomaly_event SET status='pending', workflow_id=NULL, updated_at=now() WHERE workflow_id=%s",
                (workflow_id,),
            )
            cur.execute("DELETE FROM agent_workflow WHERE id=%s", (workflow_id,))
            conn.commit()

    def mark_submission_failed(self, workflow_id: UUID, error: dict[str, Any]) -> None:
        self._update_workflow(
            workflow_id,
            status="failed",
            error=error,
            anomaly_status="failed",
        )

    def reset_for_retry(self, workflow_id: UUID, expected_version: int, actor: str, reason: str) -> Workflow:
        with self.connection() as conn:
            current = self.get_workflow(workflow_id, for_update=True, conn=conn)
            if current is None:
                raise KeyError(workflow_id)
            if current.status not in {"failed", "needs_review"}:
                raise WorkflowConflictError(f"workflow status {current.status} is not retryable")
            if current.version != expected_version:
                raise WorkflowConflictError("stale workflow version")
            target = "remediation_submitting" if current.remediation_job_id else "rca_submitting"
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_workflow SET status=%s, version=version+1,
                        decision_actor=%s, decision_reason=%s, error=NULL, updated_at=now()
                    WHERE id=%s RETURNING *
                    """,
                    (target, actor, reason, workflow_id),
                )
                row = cur.fetchone()
            conn.commit()
            return Workflow.model_validate(row)

    def _update_workflow(
        self,
        workflow_id: UUID,
        *,
        status: str,
        rca_job_id: UUID | None = None,
        remediation_job_id: UUID | None = None,
        error: dict[str, Any] | None = None,
        completed: bool = False,
        anomaly_status: str | None = None,
    ) -> None:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_workflow SET status=%s,
                    rca_job_id=COALESCE(%s, rca_job_id),
                    remediation_job_id=COALESCE(%s, remediation_job_id),
                    error=%s, version=version+1, updated_at=now(),
                    started_at=COALESCE(started_at, now()),
                    completed_at=CASE WHEN %s THEN now() ELSE completed_at END
                WHERE id=%s
                """,
                (status, rca_job_id, remediation_job_id, Jsonb(error) if error else None, completed, workflow_id),
            )
            if anomaly_status:
                cur.execute(
                    "UPDATE anomaly_event SET status=%s, updated_at=now() WHERE workflow_id=%s",
                    (anomaly_status, workflow_id),
                )
            conn.commit()
