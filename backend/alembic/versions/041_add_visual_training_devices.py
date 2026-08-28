"""add visual training devices

Revision ID: 041_visual_devices
Revises: 040_visual_training
"""

from alembic import op
import sqlalchemy as sa


revision = "041_visual_devices"
down_revision = "040_visual_training"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "visual_training_runs",
        sa.Column("requested_device", sa.String(length=12), nullable=False, server_default="auto"),
    )
    op.add_column("visual_training_runs", sa.Column("used_device", sa.String(length=12), nullable=True))
    op.add_column("visual_training_runs", sa.Column("device_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("visual_training_runs", "device_name")
    op.drop_column("visual_training_runs", "used_device")
    op.drop_column("visual_training_runs", "requested_device")
