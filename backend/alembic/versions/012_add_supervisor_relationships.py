"""add supervisor agent relationships"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_supervisor_agents"
down_revision: Union[str, None] = "011_collections_rag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("agent_type", sa.String(length=20), nullable=False, server_default="normal"),
    )
    op.add_column("agents", sa.Column("supervisor_id", sa.UUID(), nullable=True))
    op.create_check_constraint(
        "ck_agents_agent_type", "agents", "agent_type IN ('normal', 'supervisor')"
    )
    op.create_foreign_key(
        "fk_agents_supervisor_id_agents",
        "agents",
        "agents",
        ["supervisor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_agents_supervisor_id", "agents", ["supervisor_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agents_supervisor_id", table_name="agents")
    op.drop_constraint("fk_agents_supervisor_id_agents", "agents", type_="foreignkey")
    op.drop_constraint("ck_agents_agent_type", "agents", type_="check")
    op.drop_column("agents", "supervisor_id")
    op.drop_column("agents", "agent_type")
