"""add configurable router agents"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "024_router_agents"
down_revision: Union[str, None] = "023_active_prompt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_agents_agent_type", "agents", type_="check")
    op.create_check_constraint(
        "ck_agents_agent_type", "agents",
        "agent_type IN ('normal', 'supervisor', 'router')",
    )
    op.create_table(
        "router_agents",
        sa.Column("router_id", sa.UUID(), nullable=False),
        sa.Column("target_agent_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["router_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("router_id", "target_agent_id"),
    )


def downgrade() -> None:
    op.drop_table("router_agents")
    op.drop_constraint("ck_agents_agent_type", "agents", type_="check")
    op.create_check_constraint(
        "ck_agents_agent_type", "agents",
        "agent_type IN ('normal', 'supervisor')",
    )
