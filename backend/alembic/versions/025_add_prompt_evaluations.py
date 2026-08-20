"""add prompt version evaluations"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "025_prompt_evaluations"
down_revision: Union[str, None] = "024_router_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_prompt_versions", sa.Column("evaluation", sa.JSON(), nullable=True))
    op.add_column(
        "agent_prompt_versions",
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_prompt_versions", "evaluated_at")
    op.drop_column("agent_prompt_versions", "evaluation")
