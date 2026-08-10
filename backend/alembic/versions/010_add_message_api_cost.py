"""add message api cost

Revision ID: 010_message_api_cost
Revises: 009_relax_cv_schema
Create Date: 2026-08-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_message_api_cost"
down_revision: Union[str, None] = "009_relax_cv_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("api_cost_usd", sa.Float(), nullable=False, server_default="0"),
    )
    op.alter_column("messages", "api_cost_usd", server_default=None)


def downgrade() -> None:
    op.drop_column("messages", "api_cost_usd")
