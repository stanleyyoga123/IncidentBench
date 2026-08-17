"""Replace the legacy CloudAgent workflow with API-service job tables.

Revision ID: 20260817_0002
Revises: 20260817_0001
Create Date: 2026-08-17

The upgrade intentionally deletes legacy workflow data. For an online upgrade
with non-empty legacy tables, ALLOW_AGENT_WORKFLOW_RESET=true is required.
"""

from __future__ import annotations

import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260817_0002"
down_revision: Union[str, None] = "20260817_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_TABLES = (
    "remediation_ansible_run",
    "remediation",
    "completed",
    "in_progress",
    "detected_anomaly",
)


def _require_destructive_reset() -> None:
    context = op.get_context()
    if context.as_sql:
        return

    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    non_empty = []
    for table_name in LEGACY_TABLES:
        if table_name not in existing:
            continue
        count = bind.execute(
            sa.text(f'SELECT COUNT(*) FROM "{table_name}"')
        ).scalar_one()
        if count:
            non_empty.append(f"{table_name}={count}")

    allowed = os.environ.get("ALLOW_AGENT_WORKFLOW_RESET", "").lower()
    if non_empty and allowed not in {"1", "true", "yes"}:
        raise RuntimeError(
            "Refusing to delete non-empty legacy agent workflow tables "
            f"({', '.join(non_empty)}). Set "
            "ALLOW_AGENT_WORKFLOW_RESET=true for the coordinated reset."
        )


def _timestamps() -> tuple[sa.Column, ...]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    _require_destructive_reset()
    for table_name in LEGACY_TABLES:
        op.drop_table(table_name)

    uuid_type = postgresql.UUID(as_uuid=True)
    json_type = postgresql.JSONB(astext_type=sa.Text())

    op.create_table(
        "agent_workflow",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("rca_job_id", uuid_type, nullable=True),
        sa.Column("remediation_job_id", uuid_type, nullable=True),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("decision_actor", sa.Text(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("error", json_type, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("version >= 1", name="ck_agent_workflow_version"),
    )
    op.create_index("ix_agent_workflow_status", "agent_workflow", ["status"])

    op.create_table(
        "anomaly_event",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False, unique=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("profile_id", sa.Text(), nullable=True),
        sa.Column("profile_version", sa.Integer(), nullable=True),
        sa.Column("profile_parameters", json_type, nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column(
            "workflow_id",
            uuid_type,
            sa.ForeignKey("agent_workflow.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *_timestamps(),
    )
    op.create_index(
        "ix_anomaly_event_pending",
        "anomaly_event",
        ["status", "detected_at"],
    )

    op.create_table(
        "agent_execution_slot",
        sa.Column("id", sa.SmallInteger(), primary_key=True, nullable=False),
        sa.Column("holder_type", sa.Text(), nullable=True),
        sa.Column("holder_job_id", uuid_type, nullable=True),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_agent_execution_slot_singleton"),
    )
    op.execute(
        sa.text("INSERT INTO agent_execution_slot (id) VALUES (1)")
    )

    op.create_table(
        "rca_job",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "workflow_id",
            uuid_type,
            sa.ForeignKey("agent_workflow.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("request", json_type, nullable=False),
        sa.Column("result", json_type, nullable=True),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("error", json_type, nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("attempts >= 0", name="ck_rca_job_attempts"),
    )
    op.create_index("ix_rca_job_status", "rca_job", ["status", "created_at"])

    op.create_table(
        "remediation_job",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "workflow_id",
            uuid_type,
            sa.ForeignKey("agent_workflow.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "rca_job_id",
            uuid_type,
            sa.ForeignKey("rca_job.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("request", json_type, nullable=False),
        sa.Column("result", json_type, nullable=True),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("error", json_type, nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("attempts >= 0", name="ck_remediation_job_attempts"),
    )
    op.create_index(
        "ix_remediation_job_status",
        "remediation_job",
        ["status", "created_at"],
    )
    op.create_foreign_key(
        "fk_agent_workflow_rca_job",
        "agent_workflow", "rca_job", ["rca_job_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_workflow_remediation_job",
        "agent_workflow", "remediation_job", ["remediation_job_id"], ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "agent_tool_call",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("service", sa.Text(), nullable=False),
        sa.Column("job_id", uuid_type, nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("arguments", json_type, nullable=False),
        sa.Column("result", json_type, nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_agent_tool_call_job", "agent_tool_call", ["job_id"])

    op.create_table(
        "remediation_artifact",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "remediation_job_id",
            uuid_type,
            sa.ForeignKey("remediation_job.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "remediation_job_id",
            "filename",
            name="uq_remediation_artifact_job_filename",
        ),
    )


def downgrade() -> None:
    op.drop_table("remediation_artifact")
    op.drop_index("ix_agent_tool_call_job", table_name="agent_tool_call")
    op.drop_table("agent_tool_call")
    op.drop_constraint(
        "fk_agent_workflow_remediation_job",
        "agent_workflow",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_agent_workflow_rca_job",
        "agent_workflow",
        type_="foreignkey",
    )
    op.drop_index("ix_remediation_job_status", table_name="remediation_job")
    op.drop_table("remediation_job")
    op.drop_index("ix_rca_job_status", table_name="rca_job")
    op.drop_table("rca_job")
    op.drop_table("agent_execution_slot")
    op.drop_index("ix_anomaly_event_pending", table_name="anomaly_event")
    op.drop_table("anomaly_event")
    op.drop_index("ix_agent_workflow_status", table_name="agent_workflow")
    op.drop_table("agent_workflow")

    def anomaly_columns():
        return (
            sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resource", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("metrics", sa.Text(), nullable=False),
            sa.Column("method", sa.Text(), nullable=False),
            sa.Column("detail", sa.Text(), nullable=False),
        )
    for table_name in ("detected_anomaly", "in_progress", "completed"):
        op.create_table(table_name, *anomaly_columns())

    op.create_table(
        "remediation",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("anomaly_ids", postgresql.ARRAY(sa.BigInteger()), nullable=False),
        sa.Column("anomalies", postgresql.JSONB(), nullable=False),
        sa.Column("grouped_anomalies", postgresql.JSONB(), nullable=False),
        sa.Column("remediation_output", sa.Text(), nullable=False),
        sa.Column("changes", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "remediation_ansible_run",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("stdout", sa.Text(), nullable=False),
        sa.Column("ansible_file_content", sa.Text(), nullable=False),
        sa.Column("check_mode", sa.Boolean(), nullable=False),
        sa.Column("extra_vars", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
