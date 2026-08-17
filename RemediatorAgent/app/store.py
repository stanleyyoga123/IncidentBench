import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from schema import RemediationJob, RemediationJobRequest, RemediationResult


class RemediationJobStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        with Connection.connect(self.dsn, row_factory=dict_row) as conn:
            yield conn

    def create(self, request: RemediationJobRequest, key: str) -> RemediationJob:
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
                (uuid4(), key, request.workflow_id, request.rca_job_id, Jsonb(request.model_dump(mode="json"))),
            )
            row = cur.fetchone()
            conn.commit()
            return RemediationJob.model_validate(row)

    def get(self, job_id: UUID) -> RemediationJob | None:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM remediation_job WHERE id=%s", (job_id,))
            row = cur.fetchone()
            return RemediationJob.model_validate(row) if row else None

    def claim(self, owner: str, lease_seconds: int) -> RemediationJob | None:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM agent_execution_slot WHERE id=1 FOR UPDATE")
            slot = cur.fetchone()
            now = datetime.now(timezone.utc)
            if slot["holder_job_id"]:
                if slot["lease_expires_at"] and slot["lease_expires_at"] > now:
                    return None
                if slot["holder_type"] == "remediation":
                    cur.execute(
                        """
                        UPDATE remediation_job SET status='needs_review',
                            error=%s, lease_owner=NULL, lease_expires_at=NULL,
                            version=version+1, updated_at=now(), completed_at=now()
                        WHERE id=%s AND status='running'
                        """,
                        (
                            Jsonb({"type": "LeaseExpired", "message": "remediation outcome is ambiguous"}),
                            slot["holder_job_id"],
                        ),
                    )
                elif slot["holder_type"] == "rca":
                    cur.execute(
                        """
                        UPDATE rca_job
                        SET status=CASE WHEN attempts < 3 THEN 'queued' ELSE 'failed' END,
                            error=%s, lease_owner=NULL, lease_expires_at=NULL,
                            version=version+1, updated_at=now()
                        WHERE id=%s AND status='running'
                        """,
                        (
                            Jsonb({"type": "LeaseExpired", "message": "RCA worker lease expired"}),
                            slot["holder_job_id"],
                        ),
                    )
                cur.execute(
                    """UPDATE agent_execution_slot SET holder_type=NULL,
                       holder_job_id=NULL, lease_owner=NULL, lease_expires_at=NULL,
                       updated_at=now() WHERE id=1"""
                )
            cur.execute(
                "SELECT * FROM remediation_job WHERE status='queued' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
            )
            row = cur.fetchone()
            if not row:
                return None
            expiry = now + timedelta(seconds=lease_seconds)
            cur.execute(
                """
                UPDATE remediation_job SET status='running', attempts=attempts+1,
                    lease_owner=%s, lease_expires_at=%s, started_at=COALESCE(started_at, now()),
                    version=version+1, updated_at=now() WHERE id=%s RETURNING *
                """,
                (owner, expiry, row["id"]),
            )
            job = cur.fetchone()
            cur.execute(
                """
                UPDATE agent_execution_slot SET holder_type='remediation', holder_job_id=%s,
                    lease_owner=%s, lease_expires_at=%s, updated_at=now() WHERE id=1
                """,
                (row["id"], owner, expiry),
            )
            conn.commit()
            return RemediationJob.model_validate(job)

    def succeed(self, job_id: UUID, result: RemediationResult, raw: str):
        self._finish(job_id, "succeeded", result=result.model_dump(mode="json"), raw=raw)

    def renew(self, job_id: UUID, owner: str, lease_seconds: int) -> bool:
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
                    "UPDATE remediation_job SET lease_expires_at=%s, updated_at=now() WHERE id=%s AND lease_owner=%s",
                    (expiry, job_id, owner),
                )
            conn.commit()
            return renewed

    def needs_review(self, job_id: UUID, exc: Exception):
        self._finish(
            job_id,
            "needs_review",
            error={"type": type(exc).__name__, "message": str(exc)},
        )

    def record_tool_call(self, job_id: UUID, name: str, args: dict, result: Any):
        ok = not (isinstance(result, dict) and result.get("ok") is False)
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_tool_call (service, job_id, tool_name, arguments, result, ok)
                VALUES ('remediator', %s, %s, %s, %s, %s)
                """,
                (job_id, name, Jsonb(args), Jsonb(result), ok),
            )
            if name == "remediator.write_file" and ok:
                content = str(args.get("content", ""))
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
                        str(args.get("filename", "artifact")),
                        content,
                        hashlib.sha256(content.encode()).hexdigest(),
                    ),
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

    def _finish(self, job_id: UUID, status: str, *, result=None, raw=None, error=None):
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE remediation_job SET status=%s, result=%s, raw_output=%s,
                    error=%s, lease_owner=NULL, lease_expires_at=NULL,
                    version=version+1, updated_at=now(), completed_at=now()
                WHERE id=%s
                """,
                (status, Jsonb(result) if result else None, raw, Jsonb(error) if error else None, job_id),
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
