"""add message used agents

Revision ID: 013_message_used_agents
Revises: 012_supervisor_agents
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_message_used_agents"
down_revision: Union[str, None] = "012_supervisor_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("used_agents", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
    )
    op.alter_column("messages", "used_agents", server_default=None)


def downgrade() -> None:
    op.drop_column("messages", "used_agents")
