"""Create the shared anomaly workflow and remediation schema.

Revision ID: 20260817_0001
Revises:
Create Date: 2026-08-17

"""
from collections.abc import Iterable
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260817_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_table(
    table_name: str,
    columns: Iterable[sa.Column],
    existing_tables: set[str],
) -> None:
    columns = tuple(columns)
    if table_name not in existing_tables:
        op.create_table(table_name, *columns)
        existing_tables.add(table_name)
        return

    inspector = sa.inspect(op.get_bind())
    existing_columns = {
        column["name"] for column in inspector.get_columns(table_name)
    }
    required_columns = {column.name for column in columns}
    missing_columns = sorted(required_columns - existing_columns)
    if missing_columns:
        raise RuntimeError(
            f"Cannot adopt existing table {table_name!r}; missing required "
            f"columns: {', '.join(missing_columns)}"
        )


def _anomaly_columns(*, generated_id: bool) -> tuple[sa.Column, ...]:
    return (
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=generated_id,
            nullable=False,
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()") if generated_id else None,
            nullable=False,
        ),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("metrics", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
    )


def upgrade() -> None:
    migration_context = op.get_context()
    existing_tables = (
        set()
        if migration_context.as_sql
        else set(sa.inspect(op.get_bind()).get_table_names())
    )

    _ensure_table(
        "detected_anomaly",
        _anomaly_columns(generated_id=True),
        existing_tables,
    )
    _ensure_table(
        "in_progress",
        _anomaly_columns(generated_id=False),
        existing_tables,
    )
    _ensure_table(
        "completed",
        _anomaly_columns(generated_id=False),
        existing_tables,
    )
    _ensure_table(
        "remediation",
        (
            sa.Column(
                "id",
                sa.BigInteger(),
                primary_key=True,
                autoincrement=True,
                nullable=False,
            ),
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column(
                "anomaly_ids",
                postgresql.ARRAY(sa.BigInteger()),
                nullable=False,
            ),
            sa.Column("anomalies", postgresql.JSONB(), nullable=False),
            sa.Column("grouped_anomalies", postgresql.JSONB(), nullable=False),
            sa.Column("remediation_output", sa.Text(), nullable=False),
            sa.Column("changes", postgresql.JSONB(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        ),
        existing_tables,
    )
    _ensure_table(
        "remediation_ansible_run",
        (
            sa.Column(
                "id",
                sa.BigInteger(),
                primary_key=True,
                autoincrement=True,
                nullable=False,
            ),
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column("stdout", sa.Text(), nullable=False),
            sa.Column("ansible_file_content", sa.Text(), nullable=False),
            sa.Column("check_mode", sa.Boolean(), nullable=False),
            sa.Column("extra_vars", postgresql.JSONB(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        ),
        existing_tables,
    )


def downgrade() -> None:
    op.drop_table("remediation_ansible_run")
    op.drop_table("remediation")
    op.drop_table("completed")
    op.drop_table("in_progress")
    op.drop_table("detected_anomaly")

