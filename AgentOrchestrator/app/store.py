from __future__ import annotations

import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Literal
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from schema import AnomalyEventInput, RCAJob, RemediationJob, Workflow


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

    def create_rca_job(self, request: dict[str, Any], idempotency_key: str) -> RCAJob:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rca_job (id, idempotency_key, workflow_id, status, request)
                VALUES (%s, %s, %s, 'queued', %s)
                ON CONFLICT (idempotency_key) DO UPDATE
                SET idempotency_key=EXCLUDED.idempotency_key
                RETURNING *
                """,
                (
                    uuid4(),
                    idempotency_key,
                    request.get("workflow_id"),
                    Jsonb(request),
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return RCAJob.model_validate(row)

    def get_rca_job(self, job_id: UUID) -> RCAJob | None:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rca_job WHERE id=%s", (job_id,))
            row = cur.fetchone()
            return RCAJob.model_validate(row) if row else None

    def create_remediation_job(
        self, request: dict[str, Any], idempotency_key: str
    ) -> RemediationJob:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO remediation_job
                    (id, idempotency_key, workflow_id, rca_job_id, status, request)
                VALUES (%s, %s, %s, %s, 'queued', %s)
                ON CONFLICT (idempotency_key) DO UPDATE
                SET idempotency_key=EXCLUDED.idempotency_key
                RETURNING *
                """,
                (
                    uuid4(),
                    idempotency_key,
                    request.get("workflow_id"),
                    request["rca_job_id"],
                    Jsonb(request),
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return RemediationJob.model_validate(row)

    def get_remediation_job(self, job_id: UUID) -> RemediationJob | None:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM remediation_job WHERE id=%s", (job_id,))
            row = cur.fetchone()
            return RemediationJob.model_validate(row) if row else None

    def claim_execution(
        self,
        service: Literal["rca", "remediation"],
        owner: str,
        lease_seconds: int,
        max_attempts: int = 3,
    ) -> RCAJob | RemediationJob | None:
        table = "rca_job" if service == "rca" else "remediation_job"
        holder_type = "rca" if service == "rca" else "remediation"
        model = RCAJob if service == "rca" else RemediationJob
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM agent_execution_slot WHERE id=1 FOR UPDATE")
            slot = cur.fetchone()
            now = datetime.now(timezone.utc)
            if slot["holder_job_id"]:
                if slot["lease_expires_at"] and slot["lease_expires_at"] > now:
                    return None
                self._reclaim_expired_holder(cur, slot, max_attempts)
            cur.execute(
                f"""
                SELECT * FROM {table} WHERE status='queued'
                ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
                """
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return None
            expiry = now + timedelta(seconds=lease_seconds)
            cur.execute(
                f"""
                UPDATE {table} SET status='running', attempts=attempts+1,
                    lease_owner=%s, lease_expires_at=%s,
                    started_at=COALESCE(started_at, now()),
                    version=version+1, updated_at=now()
                WHERE id=%s RETURNING *
                """,
                (owner, expiry, row["id"]),
            )
            job = cur.fetchone()
            cur.execute(
                """
                UPDATE agent_execution_slot SET holder_type=%s, holder_job_id=%s,
                    lease_owner=%s, lease_expires_at=%s, updated_at=now()
                WHERE id=1
                """,
                (holder_type, row["id"], owner, expiry),
            )
            conn.commit()
            return model.model_validate(job)

    def _reclaim_expired_holder(self, cur, slot, max_attempts: int) -> None:
        if slot["holder_type"] == "rca":
            cur.execute(
                """
                UPDATE rca_job
                SET status=CASE WHEN attempts < %s THEN 'queued' ELSE 'failed' END,
                    error=%s, lease_owner=NULL, lease_expires_at=NULL,
                    version=version+1, updated_at=now()
                WHERE id=%s AND status='running'
                """,
                (
                    max_attempts,
                    Jsonb({"type": "LeaseExpired", "message": "RCA worker lease expired"}),
                    slot["holder_job_id"],
                ),
            )
        elif slot["holder_type"] == "remediation":
            cur.execute(
                """
                UPDATE remediation_job SET status='needs_review',
                    error=%s, lease_owner=NULL, lease_expires_at=NULL,
                    version=version+1, updated_at=now(), completed_at=now()
                WHERE id=%s AND status='running'
                """,
                (
                    Jsonb(
                        {
                            "type": "LeaseExpired",
                            "message": "remediation outcome is ambiguous",
                        }
                    ),
                    slot["holder_job_id"],
                ),
            )
        cur.execute(
            """
            UPDATE agent_execution_slot SET holder_type=NULL,
                holder_job_id=NULL, lease_owner=NULL, lease_expires_at=NULL,
                updated_at=now() WHERE id=1
            """
        )

    def renew_execution(
        self,
        service: Literal["rca", "remediation"],
        job_id: UUID,
        owner: str,
        lease_seconds: int,
    ) -> bool:
        table = "rca_job" if service == "rca" else "remediation_job"
        expiry = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_execution_slot SET lease_expires_at=%s, updated_at=now()
                WHERE id=1 AND holder_job_id=%s AND lease_owner=%s
                """,
                (expiry, job_id, owner),
            )
            renewed = cur.rowcount == 1
            if renewed:
                cur.execute(
                    f"""
                    UPDATE {table} SET lease_expires_at=%s, updated_at=now()
                    WHERE id=%s AND lease_owner=%s
                    """,
                    (expiry, job_id, owner),
                )
            conn.commit()
            return renewed

    def finish_rca_job(
        self,
        job_id: UUID,
        outcome: Literal["succeeded", "failed"],
        *,
        result: dict[str, Any] | None = None,
        raw_output: str | None = None,
        error: dict[str, Any] | None = None,
        max_attempts: int = 3,
    ) -> RCAJob | None:
        job = self.get_rca_job(job_id)
        if job is None:
            return None
        status = outcome
        if outcome == "failed":
            status = "queued" if job.attempts < max_attempts else "failed"
        self._finish_job("rca_job", job_id, status, result=result, raw=raw_output, error=error)
        return self.get_rca_job(job_id)

    def finish_remediation_job(
        self,
        job_id: UUID,
        status: Literal["succeeded", "needs_review"],
        *,
        result: dict[str, Any] | None = None,
        raw_output: str | None = None,
        error: dict[str, Any] | None = None,
    ) -> RemediationJob | None:
        if self.get_remediation_job(job_id) is None:
            return None
        self._finish_job(
            "remediation_job",
            job_id,
            status,
            result=result,
            raw=raw_output,
            error=error,
            completed=True,
        )
        return self.get_remediation_job(job_id)

    def _finish_job(
        self,
        table: str,
        job_id: UUID,
        status: str,
        *,
        result=None,
        raw=None,
        error=None,
        completed: bool | None = None,
    ) -> None:
        if completed is None:
            completed = status in {"succeeded", "failed", "needs_review"}
        with self.connection() as conn, conn.cursor() as cur:
            if completed is True:
                cur.execute(
                    f"""
                    UPDATE {table} SET status=%s, result=%s, raw_output=%s, error=%s,
                        lease_owner=NULL, lease_expires_at=NULL, version=version+1,
                        updated_at=now(), completed_at=now()
                    WHERE id=%s
                    """,
                    (
                        status,
                        Jsonb(result) if result is not None else None,
                        raw,
                        Jsonb(error) if error is not None else None,
                        job_id,
                    ),
                )
            else:
                cur.execute(
                    f"""
                    UPDATE {table} SET status=%s, result=%s, raw_output=%s, error=%s,
                        lease_owner=NULL, lease_expires_at=NULL, version=version+1,
                        updated_at=now(),
                        completed_at=CASE WHEN %s IN ('succeeded','failed') THEN now() ELSE NULL END
                    WHERE id=%s
                    """,
                    (
                        status,
                        Jsonb(result) if result is not None else None,
                        raw,
                        Jsonb(error) if error is not None else None,
                        status,
                        job_id,
                    ),
                )
            cur.execute(
                """
                UPDATE agent_execution_slot SET holder_type=NULL, holder_job_id=NULL,
                    lease_owner=NULL, lease_expires_at=NULL, updated_at=now()
                WHERE id=1 AND holder_job_id=%s
                """,
                (job_id,),
            )
            conn.commit()

    def record_tool_call(
        self,
        service: Literal["rca", "remediator"],
        job_id: UUID,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> None:
        ok = not (isinstance(result, dict) and result.get("ok") is False)
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_tool_call (service, job_id, tool_name, arguments, result, ok)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (service, job_id, tool_name, Jsonb(arguments), Jsonb(result), ok),
            )
            if service == "remediator" and tool_name == "remediator.write_file" and ok:
                content = str(arguments.get("content", ""))
                filename = str(arguments.get("filename", "artifact"))
                cur.execute(
                    """
                    INSERT INTO remediation_artifact
                        (remediation_job_id, filename, content, sha256)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (remediation_job_id, filename) DO UPDATE
                    SET content=EXCLUDED.content, sha256=EXCLUDED.sha256
                    """,
                    (
                        job_id,
                        filename,
                        content,
                        hashlib.sha256(content.encode()).hexdigest(),
                    ),
                )
            conn.commit()

    def upsert_artifact(self, job_id: UUID, filename: str, content: str) -> None:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO remediation_artifact
                    (remediation_job_id, filename, content, sha256)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (remediation_job_id, filename) DO UPDATE
                SET content=EXCLUDED.content, sha256=EXCLUDED.sha256
                """,
                (job_id, filename, content, hashlib.sha256(content.encode()).hexdigest()),
            )
            conn.commit()

    def list_artifacts(self, job_id: UUID) -> list[str]:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT filename FROM remediation_artifact
                WHERE remediation_job_id=%s ORDER BY filename
                """,
                (job_id,),
            )
            return [row["filename"] for row in cur.fetchall()]

