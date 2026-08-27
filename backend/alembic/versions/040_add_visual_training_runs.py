"""add visual training runs

Revision ID: 040_visual_training
Revises: 039_visual_datasets
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "040_visual_training"
down_revision = "039_visual_datasets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visual_training_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visual_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("epochs", sa.Integer(), nullable=False),
        sa.Column("batch_size", sa.Integer(), nullable=False),
        sa.Column("validation_split", sa.Float(), nullable=False),
        sa.Column("learning_rate", sa.Float(), nullable=False),
        sa.Column("current_epoch", sa.Integer(), nullable=False),
        sa.Column("metrics", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact_path", sa.String(length=500), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["visual_model_id"], ["visual_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_visual_training_runs_tenant_id", "visual_training_runs", ["tenant_id"])
    op.create_index("ix_visual_training_runs_visual_model_id", "visual_training_runs", ["visual_model_id"])


def downgrade() -> None:
    op.drop_index("ix_visual_training_runs_visual_model_id", table_name="visual_training_runs")
    op.drop_index("ix_visual_training_runs_tenant_id", table_name="visual_training_runs")
    op.drop_table("visual_training_runs")
