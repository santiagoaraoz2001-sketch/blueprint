"""Add blueprint_artifact_cache table for file-based artifact caching with SHA-256 verification.

Revision ID: 0006_artifact_cache
Revises: 0005_run_project_id
Create Date: 2026-03-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0006_artifact_cache'
down_revision: Union[str, Sequence[str]] = '0005_run_project_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'blueprint_artifact_cache',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('node_id', sa.String(), nullable=False),
        sa.Column('port_id', sa.String(), nullable=False),
        sa.Column('data_type', sa.String(), nullable=False),
        sa.Column('serializer', sa.String(), nullable=False),
        sa.Column('content_hash', sa.String(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('preview_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['blueprint_runs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_artifact_cache_run_id', 'blueprint_artifact_cache', ['run_id'])
    op.create_index('ix_artifact_cache_run_node', 'blueprint_artifact_cache', ['run_id', 'node_id'])


def downgrade() -> None:
    op.drop_index('ix_artifact_cache_run_node', 'blueprint_artifact_cache')
    op.drop_index('ix_artifact_cache_run_id', 'blueprint_artifact_cache')
    op.drop_table('blueprint_artifact_cache')
