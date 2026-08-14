"""add generated files"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020_generated_files"
down_revision: Union[str, None] = "019_workflow_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generated_files",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("template_id", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_generated_files_tenant_id", "generated_files", ["tenant_id"])
    op.create_index("ix_generated_files_agent_id", "generated_files", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_generated_files_agent_id", table_name="generated_files")
    op.drop_index("ix_generated_files_tenant_id", table_name="generated_files")
    op.drop_table("generated_files")
