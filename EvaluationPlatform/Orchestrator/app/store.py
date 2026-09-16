from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Literal
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from schema import (
    AnomalyEventInput,
    IncidentLesson,
    LearningJob,
    RCAJob,
    RemediationJob,
    Workflow,
)


class WorkflowConflictError(RuntimeError):
    pass


class WorkflowStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def running_guard(self):
        from evaluation import EvaluationStore
        return EvaluationStore(self).running()

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
                        id, event_id, detected_at, namespace, resource, name, metric, method,
                        detail, profile_id, profile_version, profile_parameters,
                        payload, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                    ON CONFLICT (event_id) DO NOTHING
                    RETURNING id
                    """,
                    (
                        uuid4(), anomaly.event_id, anomaly.detected_at, anomaly.namespace,
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
                SELECT namespace FROM anomaly_event
                WHERE status = 'pending'
                ORDER BY detected_at, created_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            )
            scope = cur.fetchone()
            if scope is None:
                return None
            cur.execute(
                """
                SELECT id, payload FROM anomaly_event
                WHERE status = 'pending'
                  AND namespace IS NOT DISTINCT FROM %s
                ORDER BY detected_at, created_at
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (scope["namespace"], limit),
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
                WHERE status IN ('rca_queued', 'rca_running', 'awaiting_approval',
                                 'remediation_queued', 'remediation_running',
                                 'learning_submitting', 'learning_queued',
                                 'learning_running', 'needs_review')
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
            remediation_required = (result or {}).get("remediation_required") is True
            workflow_status = "awaiting_approval" if remediation_required else "learning_submitting"
            self._update_workflow(
                workflow_id,
                status=workflow_status,
                error=None,
                learning_status=None if remediation_required else "pending",
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
                status="learning_submitting",
                error=None,
                learning_status="pending",
                anomaly_status="learning_submitting",
            )
        elif status in {"failed", "needs_review"}:
            self._update_workflow(
                workflow_id,
                status="failed",
                error=error,
                anomaly_status="failed",
                completed=True,
            )
        else:
            self._update_workflow(
                workflow_id,
                status="remediation_running",
                anomaly_status="remediation_running",
            )

    def attach_learning_job(self, workflow_id: UUID, job_id: UUID) -> None:
        self._update_workflow(
            workflow_id,
            status="learning_queued",
            learning_job_id=job_id,
            learning_status="queued",
            learning_error=None,
            anomaly_status="learning_queued",
        )

    def set_learning_state(
        self, workflow_id: UUID, status: str, *, error=None
    ) -> None:
        current = self.get_workflow(workflow_id)
        if current is None:
            raise KeyError(workflow_id)
        if status in {"succeeded", "failed"}:
            final_status = (
                "completed_remediated"
                if current.remediation_job_id is not None
                else "completed_no_action"
            )
            self._update_workflow(
                workflow_id,
                status=final_status,
                learning_status=status,
                learning_error=error,
                completed=True,
                anomaly_status=final_status,
            )
            return
        workflow_status = "learning_running" if status == "running" else "learning_queued"
        self._update_workflow(
            workflow_id,
            status=workflow_status,
            learning_status=status,
            learning_error=error,
            anomaly_status=workflow_status,
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
        learning_job_id: UUID | None = None,
        error: dict[str, Any] | None = None,
        learning_status: str | None = None,
        learning_error: dict[str, Any] | None = None,
        completed: bool = False,
        anomaly_status: str | None = None,
    ) -> None:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_workflow SET status=%s,
                    rca_job_id=COALESCE(%s, rca_job_id),
                    remediation_job_id=COALESCE(%s, remediation_job_id),
                    learning_job_id=COALESCE(%s, learning_job_id),
                    error=%s, learning_status=COALESCE(%s, learning_status),
                    learning_error=%s, version=version+1, updated_at=now(),
                    started_at=COALESCE(started_at, now()),
                    completed_at=CASE WHEN %s THEN now() ELSE completed_at END
                WHERE id=%s
                """,
                (
                    status,
                    rca_job_id,
                    remediation_job_id,
                    learning_job_id,
                    Jsonb(error) if error else None,
                    learning_status,
                    Jsonb(learning_error) if learning_error else None,
                    completed,
                    workflow_id,
                ),
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

    def create_learning_job(
        self, request: dict[str, Any], idempotency_key: str
    ) -> LearningJob:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO learning_job
                    (id, idempotency_key, workflow_id, status, request)
                VALUES (%s, %s, %s, 'queued', %s)
                ON CONFLICT (idempotency_key) DO UPDATE
                SET idempotency_key=EXCLUDED.idempotency_key
                RETURNING *
                """,
                (
                    uuid4(),
                    idempotency_key,
                    request["workflow_id"],
                    Jsonb(request),
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return LearningJob.model_validate(row)

    def get_learning_job(self, job_id: UUID) -> LearningJob | None:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM learning_job WHERE id=%s", (job_id,))
            row = cur.fetchone()
            return LearningJob.model_validate(row) if row else None

    def claim_execution(
        self,
        service: Literal["rca", "remediation", "learning"],
        owner: str,
        lease_seconds: int,
        max_attempts: int = 3,
    ) -> RCAJob | RemediationJob | LearningJob | None:
        table, model = {
            "rca": ("rca_job", RCAJob),
            "remediation": ("remediation_job", RemediationJob),
            "learning": ("learning_job", LearningJob),
        }[service]
        holder_type = service
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM agent_execution_slot WHERE id=1 FOR UPDATE")
            slot = cur.fetchone()
            if slot is None:
                cur.execute(
                    "INSERT INTO agent_execution_slot (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
                )
                cur.execute("SELECT * FROM agent_execution_slot WHERE id=1 FOR UPDATE")
                slot = cur.fetchone()
            now = datetime.now(timezone.utc)
            expires = slot["lease_expires_at"]
            if expires is not None and expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if slot["holder_job_id"]:
                if expires and expires > now:
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
                UPDATE remediation_job SET status='failed',
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
        elif slot["holder_type"] == "learning":
            cur.execute(
                """
                UPDATE learning_job
                SET status=CASE WHEN attempts < %s THEN 'queued' ELSE 'failed' END,
                    error=%s, lease_owner=NULL, lease_expires_at=NULL,
                    version=version+1, updated_at=now(),
                    completed_at=CASE WHEN attempts >= %s THEN now() ELSE NULL END
                WHERE id=%s AND status='running'
                """,
                (
                    max_attempts,
                    Jsonb(
                        {
                            "type": "LeaseExpired",
                            "message": "LearningAgent worker lease expired",
                        }
                    ),
                    max_attempts,
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
        service: Literal["rca", "remediation", "learning"],
        job_id: UUID,
        owner: str,
        lease_seconds: int,
    ) -> bool:
        table = {
            "rca": "rca_job",
            "remediation": "remediation_job",
            "learning": "learning_job",
        }[service]
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
        status: Literal["succeeded", "failed", "needs_review"],
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
            "failed" if status == "needs_review" else status,
            result=result,
            raw=raw_output,
            error=error,
            completed=True,
        )
        return self.get_remediation_job(job_id)

    def finish_learning_job(
        self,
        job_id: UUID,
        outcome: Literal["succeeded", "failed"],
        *,
        result: dict[str, Any] | None = None,
        raw_output: str | None = None,
        error: dict[str, Any] | None = None,
        max_attempts: int = 3,
    ) -> LearningJob | None:
        job = self.get_learning_job(job_id)
        if job is None:
            return None
        status = outcome
        if outcome == "failed":
            status = "queued" if job.attempts < max_attempts else "failed"
        if status == "succeeded":
            self._finish_learning_success(job, result or {}, raw_output, error)
        else:
            self._finish_job(
                "learning_job",
                job_id,
                status,
                result=result,
                raw=raw_output,
                error=error,
            )
        return self.get_learning_job(job_id)

    def _finish_learning_success(
        self,
        job: LearningJob,
        result: dict[str, Any],
        raw_output: str | None,
        error: dict[str, Any] | None,
    ) -> None:
        """Commit the terminal job, its lessons, and slot release atomically."""
        lessons = result.get("lessons", [])
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE learning_job
                SET status='succeeded', result=%s, raw_output=%s, error=%s,
                    lease_owner=NULL, lease_expires_at=NULL, version=version+1,
                    updated_at=now(), completed_at=now()
                WHERE id=%s
                """,
                (
                    Jsonb(result),
                    raw_output,
                    Jsonb(error) if error is not None else None,
                    job.id,
                ),
            )
            for ordinal, lesson in enumerate(lessons):
                cur.execute(
                    """
                    INSERT INTO incident_lesson (
                        id, learning_job_id, source_workflow_id, ordinal,
                        category, title, guidance, applies_when, avoid,
                        evidence_refs, namespace, resource, name, metric, tags, confidence
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (learning_job_id, ordinal) DO NOTHING
                    """,
                    (
                        uuid4(),
                        job.id,
                        job.workflow_id,
                        ordinal,
                        lesson["category"],
                        lesson["title"],
                        lesson["guidance"],
                        Jsonb(lesson.get("applies_when", [])),
                        Jsonb(lesson.get("avoid", [])),
                        Jsonb(lesson.get("evidence_refs", [])),
                        lesson.get("namespace"),
                        lesson.get("resource"),
                        lesson.get("name"),
                        lesson.get("metric"),
                        Jsonb(lesson.get("tags", [])),
                        lesson["confidence"],
                    ),
                )
            cur.execute(
                """
                UPDATE agent_execution_slot SET holder_type=NULL, holder_job_id=NULL,
                    lease_owner=NULL, lease_expires_at=NULL, updated_at=now()
                WHERE id=1 AND holder_job_id=%s
                """,
                (job.id,),
            )
            conn.commit()

    def tool_calls_for_workflow(self, workflow: Workflow) -> list[dict[str, Any]]:
        job_ids = [
            job_id
            for job_id in (workflow.rca_job_id, workflow.remediation_job_id)
            if job_id is not None
        ]
        if not job_ids:
            return []
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, service, job_id, tool_name, arguments, result, ok,
                       created_at
                FROM agent_tool_call
                WHERE job_id = ANY(%s)
                ORDER BY created_at, id
                """,
                (job_ids,),
            )
            return [dict(row) for row in cur.fetchall()]

    def retrieve_lessons(
        self,
        anomalies: list[dict[str, Any]],
        *,
        limit: int = 40,
        character_budget: int = 24_000,
    ) -> list[dict[str, Any]]:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM incident_lesson
                WHERE active=true
                ORDER BY created_at DESC
                """
            )
            candidates = [IncidentLesson.model_validate(row) for row in cur.fetchall()]

        def score(lesson: IncidentLesson) -> tuple[int, datetime]:
            best = 0
            for anomaly in anomalies:
                namespace = (
                    lesson.namespace is not None
                    and lesson.namespace == anomaly.get("namespace")
                )
                if lesson.namespace is not None and not namespace:
                    continue
                name = lesson.name is not None and lesson.name == anomaly.get("name")
                metric = lesson.metric is not None and lesson.metric == anomaly.get("metric")
                resource = (
                    lesson.resource is not None
                    and lesson.resource == anomaly.get("resource")
                )
                if name and metric and resource:
                    best = max(best, 450 if namespace else 400)
                elif metric and resource:
                    best = max(best, 350 if namespace else 300)
                elif metric:
                    best = max(best, 250 if namespace else 200)
                elif resource:
                    best = max(best, 150 if namespace else 100)
            return best, lesson.created_at

        ranked = sorted(candidates, key=score, reverse=True)
        selected: list[dict[str, Any]] = []
        used = 0
        for lesson in ranked:
            payload = lesson.model_dump(mode="json")
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            if used + len(encoded) > character_budget:
                break
            selected.append(payload)
            used += len(encoded)
            if len(selected) == limit:
                break
        return selected

    def list_lessons(self, *, active: bool | None = None) -> list[IncidentLesson]:
        with self.connection() as conn, conn.cursor() as cur:
            if active is None:
                cur.execute("SELECT * FROM incident_lesson ORDER BY created_at DESC")
            else:
                cur.execute(
                    "SELECT * FROM incident_lesson WHERE active=%s ORDER BY created_at DESC",
                    (active,),
                )
            return [IncidentLesson.model_validate(row) for row in cur.fetchall()]

    def get_lesson(self, lesson_id: UUID) -> IncidentLesson | None:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM incident_lesson WHERE id=%s", (lesson_id,))
            row = cur.fetchone()
            return IncidentLesson.model_validate(row) if row else None

    def set_lesson_active(
        self,
        lesson_id: UUID,
        active: bool,
        actor: str,
        reason: str,
        expected_version: int,
    ) -> IncidentLesson:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE incident_lesson
                SET active=%s, status_actor=%s, status_reason=%s,
                    version=version+1, updated_at=now()
                WHERE id=%s AND version=%s
                RETURNING *
                """,
                (active, actor, reason, lesson_id, expected_version),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute("SELECT id FROM incident_lesson WHERE id=%s", (lesson_id,))
                if cur.fetchone() is None:
                    raise KeyError(lesson_id)
                raise WorkflowConflictError("stale lesson version")
            conn.commit()
            return IncidentLesson.model_validate(row)

    def record_agent_output(self, service, job_id, lease_owner, raw_output, result=None):
        table = {"rca": "rca_job", "remediation": "remediation_job", "learning": "learning_job"}[service]
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""UPDATE {table} SET raw_output=%s, result=COALESCE(%s, result),
                       version=version+1, updated_at=now()
                    WHERE id=%s AND status='running' AND lease_owner=%s
                      AND lease_expires_at > now()
                    RETURNING id""",
                (raw_output, Jsonb(result) if result is not None else None, job_id, lease_owner),
            )
            if cur.fetchone() is None:
                raise WorkflowConflictError("agent output requires the current running job lease")
            conn.commit()

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
                    UPDATE {table} SET status=%s, result=COALESCE(%s, result), raw_output=COALESCE(%s, raw_output), error=%s,
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
                    UPDATE {table} SET status=%s, result=COALESCE(%s, result), raw_output=COALESCE(%s, raw_output), error=%s,
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
