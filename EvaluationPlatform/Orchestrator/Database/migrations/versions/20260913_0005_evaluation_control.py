"""Durable, serial evaluation ownership and maintenance gate."""
from alembic import op
import sqlalchemy as sa

revision = "20260913_0005"
down_revision = "20260831_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evaluation_control",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("maintenance", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reset_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("id = 1", name="ck_evaluation_control_singleton"),
    )
    op.execute("INSERT INTO evaluation_control (id) VALUES (1)")


def downgrade():
    op.drop_table("evaluation_control")
