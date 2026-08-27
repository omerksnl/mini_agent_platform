"""add configurable guardrails

Revision ID: 036_configurable_guardrails
Revises: 035_parallel_workflows
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "036_configurable_guardrails"
down_revision = "035_parallel_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guardrails",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("guardrail_type", sa.String(length=40), nullable=False),
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_guardrails_tenant_name"),
    )
    op.create_index("ix_guardrails_tenant_id", "guardrails", ["tenant_id"])
    op.create_table(
        "agent_guardrails",
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("guardrail_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["guardrail_id"], ["guardrails.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("agent_id", "guardrail_id"),
    )


def downgrade() -> None:
    op.drop_table("agent_guardrails")
    op.drop_index("ix_guardrails_tenant_id", table_name="guardrails")
    op.drop_table("guardrails")
