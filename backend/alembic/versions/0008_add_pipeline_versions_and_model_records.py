"""Add pipeline_versions and model_records tables for versioning and model registry.

Revision ID: 0008_versions_models
Revises: 0007_merge
Create Date: 2026-03-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0008_versions_models'
down_revision: Union[str, Sequence[str]] = '0007_merge'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Pipeline versions table
    op.create_table(
        'blueprint_pipeline_versions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('pipeline_id', sa.String(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('snapshot', sa.Text(), nullable=False),
        sa.Column('author', sa.String(), default='local'),
        sa.Column('message', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['pipeline_id'], ['blueprint_pipelines.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_pipeline_versions_pipeline_id',
        'blueprint_pipeline_versions',
        ['pipeline_id'],
    )
    op.create_unique_constraint(
        'uq_pipeline_version',
        'blueprint_pipeline_versions',
        ['pipeline_id', 'version_number'],
    )

    # Model records table
    op.create_table(
        'blueprint_model_records',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('version', sa.String(), default='1.0.0'),
        sa.Column('format', sa.String(), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('source_run_id', sa.String(), nullable=True),
        sa.Column('source_node_id', sa.String(), nullable=True),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('tags', sa.String(), default=''),
        sa.Column('training_config', sa.JSON(), nullable=True),
        sa.Column('source_data', sa.String(), nullable=True),
        sa.Column('model_path', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['source_run_id'], ['blueprint_runs.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('blueprint_model_records')
    op.drop_constraint('uq_pipeline_version', 'blueprint_pipeline_versions', type_='unique')
    op.drop_index('ix_pipeline_versions_pipeline_id', 'blueprint_pipeline_versions')
    op.drop_table('blueprint_pipeline_versions')
