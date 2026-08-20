"""add remote agent connections"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "027_remote_agents"
down_revision: Union[str, None] = "026_a2a_publishing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "remote_agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("agent_card_url", sa.String(length=2048), nullable=False),
        sa.Column("endpoint_url", sa.String(length=2048), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("protocol_version", sa.String(length=20), nullable=False, server_default="1.0"),
        sa.Column("skills", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "agent_card_url", name="uq_remote_agents_tenant_card_url"),
    )
    op.create_index("ix_remote_agents_tenant_id", "remote_agents", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_remote_agents_tenant_id", table_name="remote_agents")
    op.drop_table("remote_agents")
