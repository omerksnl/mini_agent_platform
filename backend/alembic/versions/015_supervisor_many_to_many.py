"""allow agents to belong to multiple supervisors"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_supervisor_many_to_many"
down_revision: Union[str, None] = "014_workflow_definitions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "supervisor_agents",
        sa.Column("supervisor_id", sa.UUID(), nullable=False),
        sa.Column("managed_agent_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["supervisor_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["managed_agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("supervisor_id", "managed_agent_id"),
    )
    op.execute(sa.text(
        "INSERT INTO supervisor_agents (supervisor_id, managed_agent_id) "
        "SELECT supervisor_id, id FROM agents WHERE supervisor_id IS NOT NULL"
    ))
    op.drop_index("ix_agents_supervisor_id", table_name="agents")
    op.drop_constraint("fk_agents_supervisor_id_agents", "agents", type_="foreignkey")
    op.drop_column("agents", "supervisor_id")


def downgrade() -> None:
    op.add_column("agents", sa.Column("supervisor_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_agents_supervisor_id_agents", "agents", "agents",
        ["supervisor_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_agents_supervisor_id", "agents", ["supervisor_id"], unique=False)
    op.execute(sa.text(
        "UPDATE agents SET supervisor_id = links.supervisor_id "
        "FROM (SELECT managed_agent_id, MIN(supervisor_id::text)::uuid AS supervisor_id "
        "FROM supervisor_agents GROUP BY managed_agent_id) AS links "
        "WHERE agents.id = links.managed_agent_id"
    ))
    op.drop_table("supervisor_agents")
