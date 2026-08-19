"""Add durable learning jobs and reusable incident lessons.

Revision ID: 20260819_0003
Revises: 20260817_0002
Create Date: 2026-08-19
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260819_0003"
down_revision: Union[str, None] = "20260817_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    json_type = postgresql.JSONB(astext_type=sa.Text())

    op.add_column("agent_workflow", sa.Column("learning_job_id", uuid_type))
    op.add_column("agent_workflow", sa.Column("learning_status", sa.Text()))
    op.add_column("agent_workflow", sa.Column("learning_error", json_type))

    op.create_table(
        "learning_job",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "workflow_id",
            uuid_type,
            sa.ForeignKey("agent_workflow.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("request", json_type, nullable=False),
        sa.Column("result", json_type),
        sa.Column("raw_output", sa.Text()),
        sa.Column("error", json_type),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lease_owner", sa.Text()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
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
        sa.CheckConstraint("attempts >= 0", name="ck_learning_job_attempts"),
        sa.CheckConstraint("version >= 1", name="ck_learning_job_version"),
    )
    op.create_index("ix_learning_job_status", "learning_job", ["status", "created_at"])
    op.create_foreign_key(
        "fk_agent_workflow_learning_job",
        "agent_workflow",
        "learning_job",
        ["learning_job_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "incident_lesson",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column(
            "learning_job_id",
            uuid_type,
            sa.ForeignKey("learning_job.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_workflow_id",
            uuid_type,
            sa.ForeignKey("agent_workflow.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("guidance", sa.Text(), nullable=False),
        sa.Column("applies_when", json_type, nullable=False),
        sa.Column("avoid", json_type, nullable=False),
        sa.Column("evidence_refs", json_type, nullable=False),
        sa.Column("resource", sa.Text()),
        sa.Column("name", sa.Text()),
        sa.Column("metric", sa.Text()),
        sa.Column("tags", json_type, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status_actor", sa.Text()),
        sa.Column("status_reason", sa.Text()),
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
        sa.CheckConstraint("ordinal >= 0", name="ck_incident_lesson_ordinal"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_incident_lesson_confidence",
        ),
        sa.CheckConstraint("version >= 1", name="ck_incident_lesson_version"),
        sa.UniqueConstraint(
            "learning_job_id", "ordinal", name="uq_incident_lesson_job_ordinal"
        ),
    )
    op.create_index(
        "ix_incident_lesson_active_scope",
        "incident_lesson",
        ["active", "resource", "name", "metric", "created_at"],
    )
    op.create_index(
        "ix_incident_lesson_confidence",
        "incident_lesson",
        ["active", "confidence", "created_at"],
    )

    # Repair clusters where the singleton row was removed after the prior migration.
    op.execute(sa.text("INSERT INTO agent_execution_slot (id) VALUES (1) ON CONFLICT (id) DO NOTHING"))


def downgrade() -> None:
    op.drop_index("ix_incident_lesson_confidence", table_name="incident_lesson")
    op.drop_index("ix_incident_lesson_active_scope", table_name="incident_lesson")
    op.drop_table("incident_lesson")
    op.drop_constraint(
        "fk_agent_workflow_learning_job", "agent_workflow", type_="foreignkey"
    )
    op.drop_index("ix_learning_job_status", table_name="learning_job")
    op.drop_table("learning_job")
    op.drop_column("agent_workflow", "learning_error")
    op.drop_column("agent_workflow", "learning_status")
    op.drop_column("agent_workflow", "learning_job_id")
