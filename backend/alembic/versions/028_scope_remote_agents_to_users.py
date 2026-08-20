"""scope remote agent connections to users"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "028_remote_agent_users"
down_revision: Union[str, None] = "027_remote_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "remote_agents",
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE remote_agents AS remote
        SET owner_user_id = (
            SELECT users.id
            FROM users
            WHERE users.tenant_id = remote.tenant_id
            ORDER BY users.created_at, users.id
            LIMIT 1
        )
        """
    )
    op.alter_column("remote_agents", "owner_user_id", nullable=False)
    op.create_foreign_key(
        "fk_remote_agents_owner_user_id_users",
        "remote_agents",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_remote_agents_owner_user_id", "remote_agents", ["owner_user_id"])
    op.drop_constraint("uq_remote_agents_tenant_card_url", "remote_agents", type_="unique")
    op.create_unique_constraint(
        "uq_remote_agents_owner_card_url",
        "remote_agents",
        ["owner_user_id", "agent_card_url"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_remote_agents_owner_card_url", "remote_agents", type_="unique")
    op.create_unique_constraint(
        "uq_remote_agents_tenant_card_url",
        "remote_agents",
        ["tenant_id", "agent_card_url"],
    )
    op.drop_index("ix_remote_agents_owner_user_id", table_name="remote_agents")
    op.drop_constraint("fk_remote_agents_owner_user_id_users", "remote_agents", type_="foreignkey")
    op.drop_column("remote_agents", "owner_user_id")
