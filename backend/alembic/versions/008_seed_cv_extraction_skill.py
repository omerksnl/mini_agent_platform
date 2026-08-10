"""seed cv extraction skill for existing tenants

Revision ID: 008_cv_skill
Revises: 007_attachments
Create Date: 2026-08-07
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.candidate_profile import (
    CANDIDATE_PROFILE_DESCRIPTION,
    CANDIDATE_PROFILE_INSTRUCTIONS,
    CANDIDATE_PROFILE_SCHEMA,
)

revision: str = "008_cv_skill"
down_revision: Union[str, None] = "007_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("""
        INSERT INTO skills (
            id, tenant_id, name, description, instructions, output_schema,
            required_system_tools, is_active, created_at, updated_at
        )
        SELECT
            gen_random_uuid(), tenants.id, 'cv_extraction', :description, :instructions,
            CAST(:output_schema AS json), CAST(:required_tools AS json), true, now(), now()
        FROM tenants
        WHERE NOT EXISTS (
            SELECT 1 FROM skills
            WHERE skills.tenant_id = tenants.id AND skills.name = 'cv_extraction'
        )
    """), {
        "description": CANDIDATE_PROFILE_DESCRIPTION,
        "instructions": CANDIDATE_PROFILE_INSTRUCTIONS,
        "output_schema": json.dumps(CANDIDATE_PROFILE_SCHEMA),
        "required_tools": json.dumps(["pdf_to_text"]),
    })


def downgrade() -> None:
    op.execute("DELETE FROM skills WHERE name = 'cv_extraction'")
