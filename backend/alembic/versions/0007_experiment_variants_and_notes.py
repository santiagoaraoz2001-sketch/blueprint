"""Add experiment variant tracking, inline notes, and run metadata columns.

Revision ID: 0007_experiment_variants
Revises: 0006_config_fingerprints
Create Date: 2026-03-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0007_experiment_variants'
down_revision: Union[str, Sequence[str]] = ('0006_config_fingerprints', '0006_artifact_cache')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Pipeline: variant tracking + notes
    op.add_column('blueprint_pipelines', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('blueprint_pipelines', sa.Column('source_pipeline_id', sa.String(), nullable=True))
    op.add_column('blueprint_pipelines', sa.Column('variant_notes', sa.Text(), nullable=True))
    op.add_column('blueprint_pipelines', sa.Column('config_diff', sa.JSON(), nullable=True))

    # Run: notes, tags, starred
    op.add_column('blueprint_runs', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('blueprint_runs', sa.Column('tags', sa.String(), nullable=True))
    op.add_column('blueprint_runs', sa.Column('starred', sa.Boolean(), server_default='0', nullable=True))


def downgrade() -> None:
    op.drop_column('blueprint_runs', 'starred')
    op.drop_column('blueprint_runs', 'tags')
    op.drop_column('blueprint_runs', 'notes')
    op.drop_column('blueprint_pipelines', 'config_diff')
    op.drop_column('blueprint_pipelines', 'variant_notes')
    op.drop_column('blueprint_pipelines', 'source_pipeline_id')
    op.drop_column('blueprint_pipelines', 'notes')
