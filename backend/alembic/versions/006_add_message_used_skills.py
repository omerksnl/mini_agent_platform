"""add used skills to messages

Revision ID: 006_message_used_skills
Revises: 005_skills
Create Date: 2026-08-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_message_used_skills"
down_revision: Union[str, None] = "005_skills"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("used_skills", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
    )
    op.alter_column("messages", "used_skills", server_default=None)


def downgrade() -> None:
    op.drop_column("messages", "used_skills")
