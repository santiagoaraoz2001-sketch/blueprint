"""Add execution_decisions table, workspace pipeline_config, and project pipeline_config columns.

Revision ID: 0007_exec_decisions
Revises: 0006_config_fingerprints
Create Date: 2026-03-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0007_exec_decisions'
down_revision: Union[str, Sequence[str]] = '0006_config_fingerprints'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # execution_decisions table
    op.create_table(
        'execution_decisions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), sa.ForeignKey('blueprint_runs.id'), nullable=False),
        sa.Column('node_id', sa.String(), nullable=False),
        sa.Column('decision', sa.String(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('cache_fingerprint', sa.String(), nullable=True),
        sa.Column('plan_hash', sa.String(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_execution_decisions_run_id', 'execution_decisions', ['run_id'])
    op.create_index('ix_execution_decisions_run_node', 'execution_decisions', ['run_id', 'node_id'])
    op.create_index('ix_execution_decisions_timestamp', 'execution_decisions', ['timestamp'])

    # workspace pipeline_config column (global overrides)
    op.add_column(
        'blueprint_workspace',
        sa.Column('pipeline_config', sa.JSON(), nullable=True),
    )

    # project pipeline_config column (project-scoped overrides)
    op.add_column(
        'blueprint_projects',
        sa.Column('pipeline_config', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('blueprint_projects', 'pipeline_config')
    op.drop_column('blueprint_workspace', 'pipeline_config')
    op.drop_index('ix_execution_decisions_timestamp', 'execution_decisions')
    op.drop_index('ix_execution_decisions_run_node', 'execution_decisions')
    op.drop_index('ix_execution_decisions_run_id', 'execution_decisions')
    op.drop_table('execution_decisions')
