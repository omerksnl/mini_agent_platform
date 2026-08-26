"""add parallel and nested workflows

Revision ID: 035_parallel_workflows
Revises: 034_a2a_byok_billing
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "035_parallel_workflows"
down_revision = "034_a2a_byok_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_workflow_steps_type", "workflow_steps", type_="check")
    op.create_check_constraint(
        "ck_workflow_steps_type",
        "workflow_steps",
        "step_type IN ('agent', 'remote_agent', 'workflow', 'http_tool', 'system_tool', 'human_wait', 'report')",
    )
    op.add_column(
        "workflow_steps",
        sa.Column("target_workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_workflow_steps_target_workflow_id",
        "workflow_steps",
        "workflows",
        ["target_workflow_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "workflow_runs",
        sa.Column("started_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_workflow_runs_started_by_user_id", "workflow_runs", ["started_by_user_id"])
    op.create_foreign_key(
        "fk_workflow_runs_started_by_user_id",
        "workflow_runs",
        "users",
        ["started_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_workflow_runs_started_by_user_id", "workflow_runs", type_="foreignkey")
    op.drop_index("ix_workflow_runs_started_by_user_id", table_name="workflow_runs")
    op.drop_column("workflow_runs", "started_by_user_id")
    op.drop_constraint("fk_workflow_steps_target_workflow_id", "workflow_steps", type_="foreignkey")
    op.drop_column("workflow_steps", "target_workflow_id")
    op.drop_constraint("ck_workflow_steps_type", "workflow_steps", type_="check")
    op.create_check_constraint(
        "ck_workflow_steps_type",
        "workflow_steps",
        "step_type IN ('agent', 'remote_agent', 'http_tool', 'system_tool', 'human_wait', 'report')",
    )
