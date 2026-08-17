"""add active agent prompt version"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023_active_prompt"
down_revision: Union[str, None] = "022_prompt_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("active_prompt_version_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_agents_active_prompt_version",
        "agents",
        "agent_prompt_versions",
        ["active_prompt_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        "UPDATE agents SET active_prompt_version_id = ("
        "SELECT id FROM agent_prompt_versions "
        "WHERE agent_prompt_versions.agent_id = agents.id "
        "ORDER BY version_number DESC LIMIT 1)"
    )


def downgrade() -> None:
    op.drop_constraint("fk_agents_active_prompt_version", "agents", type_="foreignkey")
    op.drop_column("agents", "active_prompt_version_id")
