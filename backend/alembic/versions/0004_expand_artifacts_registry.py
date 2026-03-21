"""Expand artifacts table into a full registry with lineage tracking.

Revision ID: 0004_artifacts_registry
Revises: 0003_add_sweeps
Create Date: 2026-03-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0004_artifacts_registry'
down_revision: Union[str, Sequence[str]] = '0003_add_sweeps'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename existing columns
    op.alter_column('blueprint_artifacts', 'type', new_column_name='artifact_type')
    op.alter_column('blueprint_artifacts', 'path', new_column_name='file_path')

    # Add new lineage columns (nullable initially for backfill)
    op.add_column('blueprint_artifacts', sa.Column('pipeline_id', sa.String(), nullable=True))
    op.add_column('blueprint_artifacts', sa.Column('node_id', sa.String(), nullable=True))
    op.add_column('blueprint_artifacts', sa.Column('block_type', sa.String(), nullable=True))
    op.add_column('blueprint_artifacts', sa.Column('hash', sa.String(), nullable=True))
    op.add_column('blueprint_artifacts', sa.Column('metadata', sa.JSON(), nullable=True))

    # Backfill pipeline_id from runs table for any existing rows
    op.execute("""
        UPDATE blueprint_artifacts
        SET pipeline_id = (
            SELECT blueprint_runs.pipeline_id
            FROM blueprint_runs
            WHERE blueprint_runs.id = blueprint_artifacts.run_id
        )
        WHERE pipeline_id IS NULL
    """)

    # Backfill node_id and block_type with defaults for existing rows
    op.execute("""
        UPDATE blueprint_artifacts
        SET node_id = 'unknown', block_type = 'unknown'
        WHERE node_id IS NULL
    """)

    # Enforce NOT NULL and add FK (SQLite requires batch mode for ALTER constraints)
    with op.batch_alter_table('blueprint_artifacts') as batch_op:
        batch_op.alter_column('pipeline_id', nullable=False)
        batch_op.alter_column('node_id', nullable=False)
        batch_op.alter_column('block_type', nullable=False)
        batch_op.alter_column('artifact_type', nullable=False)
        batch_op.create_foreign_key(
            'fk_artifact_pipeline', 'blueprint_pipelines', ['pipeline_id'], ['id']
        )

    # Indexes for dashboard queries
    op.create_index('ix_artifact_run_id', 'blueprint_artifacts', ['run_id'])
    op.create_index('ix_artifact_pipeline_id', 'blueprint_artifacts', ['pipeline_id'])
    op.create_index('ix_artifact_type', 'blueprint_artifacts', ['artifact_type'])
    op.create_index('ix_artifact_pipeline_type', 'blueprint_artifacts', ['pipeline_id', 'artifact_type'])


def downgrade() -> None:
    op.drop_index('ix_artifact_pipeline_type', 'blueprint_artifacts')
    op.drop_index('ix_artifact_type', 'blueprint_artifacts')
    op.drop_index('ix_artifact_pipeline_id', 'blueprint_artifacts')
    op.drop_index('ix_artifact_run_id', 'blueprint_artifacts')

    with op.batch_alter_table('blueprint_artifacts') as batch_op:
        batch_op.drop_constraint('fk_artifact_pipeline', type_='foreignkey')

    op.drop_column('blueprint_artifacts', 'metadata')
    op.drop_column('blueprint_artifacts', 'hash')
    op.drop_column('blueprint_artifacts', 'block_type')
    op.drop_column('blueprint_artifacts', 'node_id')
    op.drop_column('blueprint_artifacts', 'pipeline_id')

    op.alter_column('blueprint_artifacts', 'file_path', new_column_name='path')
    op.alter_column('blueprint_artifacts', 'artifact_type', new_column_name='type')
