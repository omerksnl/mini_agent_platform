"""add workflow run attachments"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019_workflow_attachments"
down_revision: Union[str, None] = "018_artifact_sequence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("attachments", sa.Column("workflow_run_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_attachments_workflow_run_id",
        "attachments",
        "workflow_runs",
        ["workflow_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_attachments_workflow_run_id", "attachments", ["workflow_run_id"])


def downgrade() -> None:
    op.drop_index("ix_attachments_workflow_run_id", table_name="attachments")
    op.drop_constraint("fk_attachments_workflow_run_id", "attachments", type_="foreignkey")
    op.drop_column("attachments", "workflow_run_id")
