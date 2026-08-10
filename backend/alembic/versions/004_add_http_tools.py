"""add HTTP tools and agent tool selection

Revision ID: 004_http_tools
Revises: 003_message_used_tools
Create Date: 2026-08-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_http_tools"
down_revision: Union[str, None] = "003_message_used_tools"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "system_tools",
            sa.JSON(),
            server_default=sa.text("'[\"calculator\", \"current_datetime\"]'::json"),
            nullable=False,
        ),
    )
    op.alter_column("agents", "system_tools", server_default=None)

    op.create_table(
        "http_tools",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_http_tools_tenant_name"),
    )
    op.create_index(op.f("ix_http_tools_tenant_id"), "http_tools", ["tenant_id"], unique=False)
    op.create_table(
        "agent_tools",
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tool_id"], ["http_tools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("agent_id", "tool_id"),
    )


def downgrade() -> None:
    op.drop_table("agent_tools")
    op.drop_index(op.f("ix_http_tools_tenant_id"), table_name="http_tools")
    op.drop_table("http_tools")
    op.drop_column("agents", "system_tools")
