"""add A2A BYOK billing

Revision ID: 034_a2a_byok_billing
Revises: 033_agent_provider_assignments
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "034_a2a_byok_billing"
down_revision = "033_agent_provider_assignments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("a2a_published_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_agents_a2a_published_by_user_id", "agents", ["a2a_published_by_user_id"])
    op.create_foreign_key(
        "fk_agents_a2a_published_by_user_id_users", "agents", "users",
        ["a2a_published_by_user_id"], ["id"], ondelete="SET NULL",
    )
    op.add_column("remote_agents", sa.Column("billing_mode", sa.String(length=20), server_default="owner", nullable=False))
    op.add_column("remote_agents", sa.Column("provider_credential_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_remote_agents_provider_credential_id", "remote_agents", "provider_credentials",
        ["provider_credential_id"], ["id"], ondelete="SET NULL",
    )
    op.create_table(
        "a2a_call_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("remote_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("billing_mode", sa.String(length=20), nullable=False),
        sa.Column("billed_to", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("api_cost_usd", sa.Float(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["remote_agent_id"], ["remote_agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_a2a_call_usage_tenant_id", "a2a_call_usage", ["tenant_id"])
    op.create_index("ix_a2a_call_usage_user_id", "a2a_call_usage", ["user_id"])
    op.create_index("ix_a2a_call_usage_remote_agent_id", "a2a_call_usage", ["remote_agent_id"])


def downgrade() -> None:
    op.drop_table("a2a_call_usage")
    op.drop_constraint("fk_remote_agents_provider_credential_id", "remote_agents", type_="foreignkey")
    op.drop_column("remote_agents", "provider_credential_id")
    op.drop_column("remote_agents", "billing_mode")
    op.drop_constraint("fk_agents_a2a_published_by_user_id_users", "agents", type_="foreignkey")
    op.drop_index("ix_agents_a2a_published_by_user_id", table_name="agents")
    op.drop_column("agents", "a2a_published_by_user_id")
