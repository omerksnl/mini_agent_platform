"""add workflow definitions

Revision ID: 014_workflow_definitions
Revises: 013_message_used_agents
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014_workflow_definitions"
down_revision: Union[str, None] = "013_message_used_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_workflows_tenant_name"),
    )
    op.create_index("ix_workflows_tenant_id", "workflows", ["tenant_id"], unique=False)

    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workflow_id", sa.UUID(), nullable=False),
        sa.Column("step_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("step_type", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=True),
        sa.Column("http_tool_id", sa.UUID(), nullable=True),
        sa.Column("system_tool_name", sa.String(length=100), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.CheckConstraint(
            "step_type IN ('agent', 'http_tool', 'system_tool', 'human_wait')",
            name="ck_workflow_steps_type",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["http_tool_id"], ["http_tools.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", "position", name="uq_workflow_steps_position"),
        sa.UniqueConstraint("workflow_id", "step_key", name="uq_workflow_steps_key"),
    )
    op.create_index("ix_workflow_steps_workflow_id", "workflow_steps", ["workflow_id"], unique=False)

    op.create_table(
        "workflow_routes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workflow_id", sa.UUID(), nullable=False),
        sa.Column("source_step_id", sa.UUID(), nullable=False),
        sa.Column("target_step_id", sa.UUID(), nullable=False),
        sa.Column("condition", sa.String(length=30), nullable=False, server_default="success"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.CheckConstraint(
            "condition IN ('success', 'failure', 'input_available', 'always')",
            name="ck_workflow_routes_condition",
        ),
        sa.CheckConstraint("source_step_id <> target_step_id", name="ck_workflow_routes_no_self"),
        sa.ForeignKeyConstraint(["source_step_id"], ["workflow_steps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_step_id"], ["workflow_steps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_id", "source_step_id", "target_step_id", "condition",
            name="uq_workflow_routes_edge_condition",
        ),
    )
    op.create_index("ix_workflow_routes_workflow_id", "workflow_routes", ["workflow_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_workflow_routes_workflow_id", table_name="workflow_routes")
    op.drop_table("workflow_routes")
    op.drop_index("ix_workflow_steps_workflow_id", table_name="workflow_steps")
    op.drop_table("workflow_steps")
    op.drop_index("ix_workflows_tenant_id", table_name="workflows")
    op.drop_table("workflows")
