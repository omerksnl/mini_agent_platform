"""add agent provider assignments

Revision ID: 033_agent_provider_assignments
Revises: 032_named_provider_credentials
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "033_agent_provider_assignments"
down_revision = "032_named_provider_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_provider_assignments",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_credential_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_credential_id"], ["provider_credentials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "agent_id"),
    )


def downgrade() -> None:
    op.drop_table("agent_provider_assignments")
