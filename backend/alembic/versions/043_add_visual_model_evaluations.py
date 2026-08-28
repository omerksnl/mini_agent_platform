"""add visual model evaluations

Revision ID: 043_visual_evaluations
Revises: 042_visual_versions
"""

from alembic import op
import sqlalchemy as sa


revision = "043_visual_evaluations"
down_revision = "042_visual_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "visual_training_runs",
        sa.Column("training_history", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "visual_training_runs",
        sa.Column("evaluation", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.alter_column("visual_training_runs", "training_history", server_default=None)
    op.alter_column("visual_training_runs", "evaluation", server_default=None)


def downgrade() -> None:
    op.drop_column("visual_training_runs", "evaluation")
    op.drop_column("visual_training_runs", "training_history")
