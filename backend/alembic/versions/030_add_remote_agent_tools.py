"""allow normal agents to call remote A2A agents as tools"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "030_remote_agent_tools"
down_revision: Union[str, None] = "029_remote_multiagent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_remote_tools",
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("remote_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["remote_agent_id"], ["remote_agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("agent_id", "remote_agent_id"),
    )


def downgrade() -> None:
    op.drop_table("agent_remote_tools")
