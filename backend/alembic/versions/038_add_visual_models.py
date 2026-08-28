"""add configurable visual models

Revision ID: 038_visual_models
Revises: 037_agent_collection_limit
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "038_visual_models"
down_revision = "037_agent_collection_limit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visual_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("task_type", sa.String(length=40), nullable=False, server_default="image_classification"),
        sa.Column("architecture", sa.String(length=40), nullable=False),
        sa.Column("class_names", sa.JSON(), nullable=False),
        sa.Column("image_width", sa.Integer(), nullable=False, server_default="224"),
        sa.Column("image_height", sa.Integer(), nullable=False, server_default="224"),
        sa.Column("channels", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("use_pretrained_weights", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_visual_models_tenant_name"),
    )
    op.create_index("ix_visual_models_tenant_id", "visual_models", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_visual_models_tenant_id", table_name="visual_models")
    op.drop_table("visual_models")
