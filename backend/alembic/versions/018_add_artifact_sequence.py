"""add workflow artifact sequence"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018_artifact_sequence"
down_revision: Union[str, None] = "017_workflow_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workflow_artifacts",
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("workflow_artifacts", "sequence", server_default=None)
    op.create_unique_constraint(
        "uq_workflow_artifacts_run_sequence",
        "workflow_artifacts",
        ["workflow_run_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_workflow_artifacts_run_sequence", "workflow_artifacts", type_="unique"
    )
    op.drop_column("workflow_artifacts", "sequence")
