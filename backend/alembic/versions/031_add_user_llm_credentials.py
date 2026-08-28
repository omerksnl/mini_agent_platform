"""add user llm credentials

Revision ID: 031_user_llm_credentials
Revises: 030_remote_agent_tools
"""
from alembic import op
import sqlalchemy as sa

revision = "031_user_llm_credentials"
down_revision = "030_remote_agent_tools"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("llm_provider", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("encrypted_llm_api_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "encrypted_llm_api_key")
    op.drop_column("users", "llm_provider")
