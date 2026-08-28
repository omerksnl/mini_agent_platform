"""add workflow artifacts"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017_workflow_artifacts"
down_revision: Union[str, None] = "016_workflow_execution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("workflow_run_id", sa.UUID(), nullable=False),
        sa.Column("step_run_id", sa.UUID(), nullable=True),
        sa.Column("artifact_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("artifact_type", sa.String(length=30), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "artifact_type IN ('workflow_input', 'agent_output', 'human_input', 'tool_output')",
            name="ck_workflow_artifacts_type",
        ),
        sa.ForeignKeyConstraint(["step_run_id"], ["workflow_step_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_run_id", "artifact_key", name="uq_workflow_artifacts_run_key"),
    )
    op.create_index("ix_workflow_artifacts_tenant_id", "workflow_artifacts", ["tenant_id"])
    op.create_index("ix_workflow_artifacts_workflow_run_id", "workflow_artifacts", ["workflow_run_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_artifacts_workflow_run_id", table_name="workflow_artifacts")
    op.drop_index("ix_workflow_artifacts_tenant_id", table_name="workflow_artifacts")
    op.drop_table("workflow_artifacts")
