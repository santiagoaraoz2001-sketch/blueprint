"""Add project_id to runs for direct project-scoped queries.

Revision ID: 0005_run_project_id
Revises: 0004_artifacts_registry
Create Date: 2026-03-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0005_run_project_id'
down_revision: Union[str, Sequence[str]] = '0004_artifacts_registry'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add project_id column (nullable — pipelines may not have a project)
    op.add_column('blueprint_runs', sa.Column('project_id', sa.String(), nullable=True))

    # Backfill from pipeline's project_id for existing runs
    op.execute("""
        UPDATE blueprint_runs
        SET project_id = (
            SELECT blueprint_pipelines.project_id
            FROM blueprint_pipelines
            WHERE blueprint_pipelines.id = blueprint_runs.pipeline_id
        )
        WHERE project_id IS NULL
    """)

    # Add FK and index (SQLite batch mode)
    with op.batch_alter_table('blueprint_runs') as batch_op:
        batch_op.create_foreign_key(
            'fk_run_project', 'blueprint_projects', ['project_id'], ['id']
        )

    op.create_index('ix_run_project_id', 'blueprint_runs', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_run_project_id', 'blueprint_runs')
    with op.batch_alter_table('blueprint_runs') as batch_op:
        batch_op.drop_constraint('fk_run_project', type_='foreignkey')
    op.drop_column('blueprint_runs', 'project_id')
