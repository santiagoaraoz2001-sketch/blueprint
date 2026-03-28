"""Add history_json column to blueprint_pipelines for undo/redo persistence.

Revision ID: 0007_pipeline_history
Revises: 0006_config_fingerprints, 0006_artifact_cache
Create Date: 2026-03-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0007_pipeline_history'
down_revision: Union[str, Sequence[str]] = ('0006_config_fingerprints', '0006_artifact_cache')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'blueprint_pipelines',
        sa.Column('history_json', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('blueprint_pipelines', 'history_json')
