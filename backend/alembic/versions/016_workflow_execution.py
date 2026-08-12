"""add workflow execution runs"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016_workflow_execution"
down_revision: Union[str, None] = "015_supervisor_many_to_many"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("workflow_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_step_id", sa.UUID(), nullable=True),
        sa.Column("input_data", sa.JSON(), nullable=False),
        sa.Column("output_data", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("total_api_cost_usd", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('running', 'waiting', 'completed', 'failed')", name="ck_workflow_runs_status"),
        sa.ForeignKeyConstraint(["current_step_id"], ["workflow_steps.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_runs_tenant_id", "workflow_runs", ["tenant_id"])
    op.create_index("ix_workflow_runs_workflow_id", "workflow_runs", ["workflow_id"])
    op.create_table(
        "workflow_step_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workflow_run_id", sa.UUID(), nullable=False),
        sa.Column("workflow_step_id", sa.UUID(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("step_key", sa.String(length=64), nullable=False),
        sa.Column("step_name", sa.String(length=255), nullable=False),
        sa.Column("step_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("input_data", sa.JSON(), nullable=False),
        sa.Column("output_data", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("api_cost_usd", sa.Float(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('running', 'waiting', 'completed', 'failed')", name="ck_workflow_step_runs_status"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_step_id"], ["workflow_steps.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_run_id", "sequence", name="uq_workflow_step_runs_sequence"),
    )
    op.create_index("ix_workflow_step_runs_workflow_run_id", "workflow_step_runs", ["workflow_run_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_step_runs_workflow_run_id", table_name="workflow_step_runs")
    op.drop_table("workflow_step_runs")
    op.drop_index("ix_workflow_runs_workflow_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_tenant_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
