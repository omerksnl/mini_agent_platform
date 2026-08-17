"""add agent prompt versions"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022_prompt_versions"
down_revision: Union[str, None] = "021_workflow_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_prompt_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "version_number", name="uq_agent_prompt_versions_number"),
    )
    op.create_index("ix_agent_prompt_versions_agent_id", "agent_prompt_versions", ["agent_id"])
    op.execute(
        "INSERT INTO agent_prompt_versions (id, agent_id, version_number, system_prompt) "
        "SELECT gen_random_uuid(), id, 1, system_prompt FROM agents"
    )


def downgrade() -> None:
    op.drop_index("ix_agent_prompt_versions_agent_id", table_name="agent_prompt_versions")
    op.drop_table("agent_prompt_versions")
