"""add visual model datasets

Revision ID: 039_visual_datasets
Revises: 038_visual_models
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "039_visual_datasets"
down_revision = "038_visual_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visual_dataset_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visual_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("class_name", sa.String(length=255), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["visual_model_id"], ["visual_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
        sa.UniqueConstraint("visual_model_id", "sha256", name="uq_visual_dataset_model_sha256"),
    )
    op.create_index("ix_visual_dataset_images_tenant_id", "visual_dataset_images", ["tenant_id"])
    op.create_index("ix_visual_dataset_images_visual_model_id", "visual_dataset_images", ["visual_model_id"])


def downgrade() -> None:
    op.drop_index("ix_visual_dataset_images_visual_model_id", table_name="visual_dataset_images")
    op.drop_index("ix_visual_dataset_images_tenant_id", table_name="visual_dataset_images")
    op.drop_table("visual_dataset_images")
