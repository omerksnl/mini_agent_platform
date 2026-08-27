"""add per-agent collection search limit

Revision ID: 037_agent_collection_limit
Revises: 036_configurable_guardrails
"""

from alembic import op
import sqlalchemy as sa


revision = "037_agent_collection_limit"
down_revision = "036_configurable_guardrails"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "collection_search_limit",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "collection_search_limit")
