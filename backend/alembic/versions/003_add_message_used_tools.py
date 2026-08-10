"""add used tools to messages

Revision ID: 003_message_used_tools
Revises: 002_conversations_messages
Create Date: 2026-08-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_message_used_tools"
down_revision: Union[str, None] = "002_conversations_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("used_tools", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
    )
    op.alter_column("messages", "used_tools", server_default=None)


def downgrade() -> None:
    op.drop_column("messages", "used_tools")
