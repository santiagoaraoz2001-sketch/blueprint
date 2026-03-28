"""Add presets table for config presets.

This migration also serves as the merge point for the two branches that
diverged at 0005_run_project_id:
  - 0006_artifact_cache   (adds blueprint_artifact_cache table)
  - 0006_config_fingerprints (adds config_fingerprints column to runs)

By listing both as down_revision, Alembic requires both to be applied
before this migration runs, collapsing the history back to a single head.

Revision ID: 0007_presets
Revises: 0006_config_fingerprints, 0006_artifact_cache
Create Date: 2026-03-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0007_presets'
down_revision: Union[str, Sequence[str]] = ('0006_config_fingerprints', '0006_artifact_cache')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'presets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('block_type', sa.String(), nullable=False, index=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('config_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime()),
    )


def downgrade() -> None:
    op.drop_table('presets')
