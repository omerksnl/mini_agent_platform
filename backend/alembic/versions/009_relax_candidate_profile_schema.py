"""relax candidate profile schema

Revision ID: 009_relax_cv_schema
Revises: 008_cv_skill
Create Date: 2026-08-07
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.candidate_profile import CANDIDATE_PROFILE_SCHEMA

revision: str = "009_relax_cv_schema"
down_revision: Union[str, None] = "008_cv_skill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text("UPDATE skills SET output_schema = CAST(:schema AS json), updated_at = now() WHERE name = 'cv_extraction'"),
        {"schema": json.dumps(CANDIDATE_PROFILE_SCHEMA)},
    )


def downgrade() -> None:
    pass
