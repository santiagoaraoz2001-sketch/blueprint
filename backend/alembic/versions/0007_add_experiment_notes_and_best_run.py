"""Add experiment_notes table and best_in_project column to runs.

Revision ID: 0007_experiment_notes
Revises: 0006_artifact_cache, 0006_config_fingerprints
Create Date: 2026-03-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0007_experiment_notes'
down_revision: Union[str, Sequence[str]] = ('0006_artifact_cache', '0006_config_fingerprints')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'blueprint_experiment_notes',
        sa.Column('id', sa.String, primary_key=True),
        sa.Column('run_id', sa.String, sa.ForeignKey('blueprint_runs.id'), nullable=False, index=True),
        sa.Column('auto_summary', sa.Text, nullable=False),
        sa.Column('user_notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime),
    )
    op.create_index('ix_experiment_note_created', 'blueprint_experiment_notes', ['created_at'])

    # Add best_in_project to runs
    op.add_column('blueprint_runs', sa.Column('best_in_project', sa.Boolean, server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('blueprint_runs', 'best_in_project')
    op.drop_table('blueprint_experiment_notes')
