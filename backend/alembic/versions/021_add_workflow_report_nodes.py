"""add workflow report nodes"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021_workflow_reports"
down_revision: Union[str, None] = "020_generated_files"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_workflow_steps_type", "workflow_steps", type_="check")
    op.create_check_constraint(
        "ck_workflow_steps_type", "workflow_steps",
        "step_type IN ('agent', 'http_tool', 'system_tool', 'human_wait', 'report')",
    )
    op.drop_constraint("ck_workflow_artifacts_type", "workflow_artifacts", type_="check")
    op.create_check_constraint(
        "ck_workflow_artifacts_type", "workflow_artifacts",
        "artifact_type IN ('workflow_input', 'agent_output', 'human_input', 'tool_output', 'generated_file')",
    )
    op.alter_column("generated_files", "agent_id", existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.alter_column("generated_files", "agent_id", existing_type=sa.UUID(), nullable=False)
    op.drop_constraint("ck_workflow_artifacts_type", "workflow_artifacts", type_="check")
    op.create_check_constraint(
        "ck_workflow_artifacts_type", "workflow_artifacts",
        "artifact_type IN ('workflow_input', 'agent_output', 'human_input', 'tool_output')",
    )
    op.drop_constraint("ck_workflow_steps_type", "workflow_steps", type_="check")
    op.create_check_constraint(
        "ck_workflow_steps_type", "workflow_steps",
        "step_type IN ('agent', 'http_tool', 'system_tool', 'human_wait')",
    )
