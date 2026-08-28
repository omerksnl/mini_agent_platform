"""add visual model versions

Revision ID: 042_visual_versions
Revises: 041_visual_devices
"""

from alembic import op
import sqlalchemy as sa


revision = "042_visual_versions"
down_revision = "041_visual_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("visual_training_runs", sa.Column("version_number", sa.Integer(), nullable=True))
    op.add_column(
        "visual_training_runs",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        """
        WITH numbered AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY visual_model_id
                       ORDER BY completed_at ASC NULLS LAST, created_at ASC
                   ) AS version_number,
                   ROW_NUMBER() OVER (
                       PARTITION BY visual_model_id
                       ORDER BY completed_at DESC NULLS LAST, created_at DESC
                   ) AS newest
            FROM visual_training_runs
            WHERE status = 'completed' AND artifact_path IS NOT NULL
        )
        UPDATE visual_training_runs AS runs
        SET version_number = numbered.version_number,
            is_active = (numbered.newest = 1)
        FROM numbered
        WHERE runs.id = numbered.id
        """
    )
    op.alter_column("visual_training_runs", "is_active", server_default=None)
    op.create_index(
        "ix_visual_training_runs_active_version",
        "visual_training_runs",
        ["visual_model_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_visual_training_runs_active_version", table_name="visual_training_runs")
    op.drop_column("visual_training_runs", "is_active")
    op.drop_column("visual_training_runs", "version_number")
