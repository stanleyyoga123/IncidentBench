"""Add namespace scope to anomaly events and incident lessons.

Revision ID: 20260831_0004
Revises: 20260819_0003
Create Date: 2026-08-31
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260831_0004"
down_revision: Union[str, None] = "20260819_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("anomaly_event", sa.Column("namespace", sa.Text()))
    op.execute(
        sa.text(
            "UPDATE anomaly_event SET namespace = payload->>'namespace' "
            "WHERE namespace IS NULL AND payload ? 'namespace'"
        )
    )
    op.create_index(
        "ix_anomaly_event_namespace_pending",
        "anomaly_event",
        ["namespace", "status", "detected_at"],
    )

    op.drop_index("ix_incident_lesson_active_scope", table_name="incident_lesson")
    op.add_column("incident_lesson", sa.Column("namespace", sa.Text()))
    op.create_index(
        "ix_incident_lesson_active_scope",
        "incident_lesson",
        ["active", "namespace", "resource", "name", "metric", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_incident_lesson_active_scope", table_name="incident_lesson")
    op.drop_column("incident_lesson", "namespace")
    op.create_index(
        "ix_incident_lesson_active_scope",
        "incident_lesson",
        ["active", "resource", "name", "metric", "created_at"],
    )

    op.drop_index("ix_anomaly_event_namespace_pending", table_name="anomaly_event")
    op.drop_column("anomaly_event", "namespace")
