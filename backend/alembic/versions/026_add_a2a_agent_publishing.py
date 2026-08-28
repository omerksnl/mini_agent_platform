"""add a2a agent publishing"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "026_a2a_publishing"
down_revision: Union[str, None] = "025_prompt_evaluations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("a2a_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("agents", sa.Column("a2a_description", sa.Text(), nullable=False, server_default=""))
    op.add_column("agents", sa.Column("a2a_api_key_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "a2a_api_key_hash")
    op.drop_column("agents", "a2a_description")
    op.drop_column("agents", "a2a_enabled")
