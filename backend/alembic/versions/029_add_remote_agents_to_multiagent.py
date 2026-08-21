"""add remote agents to multi-agent systems and workflows"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "029_remote_multiagent"
down_revision: Union[str, None] = "028_remote_agent_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "supervisor_remote_agents",
        sa.Column("supervisor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("remote_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["supervisor_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["remote_agent_id"], ["remote_agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("supervisor_id", "remote_agent_id"),
    )
    op.create_table(
        "router_remote_agents",
        sa.Column("router_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("remote_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["router_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["remote_agent_id"], ["remote_agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("router_id", "remote_agent_id"),
    )
    op.add_column("workflow_steps", sa.Column("remote_agent_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_workflow_steps_remote_agent_id_remote_agents",
        "workflow_steps", "remote_agents", ["remote_agent_id"], ["id"], ondelete="RESTRICT",
    )
    op.drop_constraint("ck_workflow_steps_type", "workflow_steps", type_="check")
    op.create_check_constraint(
        "ck_workflow_steps_type", "workflow_steps",
        "step_type IN ('agent', 'remote_agent', 'http_tool', 'system_tool', 'human_wait', 'report')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_workflow_steps_type", "workflow_steps", type_="check")
    op.create_check_constraint(
        "ck_workflow_steps_type", "workflow_steps",
        "step_type IN ('agent', 'http_tool', 'system_tool', 'human_wait', 'report')",
    )
    op.drop_constraint("fk_workflow_steps_remote_agent_id_remote_agents", "workflow_steps", type_="foreignkey")
    op.drop_column("workflow_steps", "remote_agent_id")
    op.drop_table("router_remote_agents")
    op.drop_table("supervisor_remote_agents")
