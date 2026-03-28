"""Add blueprint_execution_decisions table for replay inspector.

Revision ID: 0007_execution_decisions
Revises: 0006_artifact_cache, 0006_config_fingerprints
Create Date: 2026-03-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0007_execution_decisions'
down_revision: Union[str, Sequence[str]] = ('0006_artifact_cache', '0006_config_fingerprints')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'blueprint_execution_decisions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('node_id', sa.String(), nullable=False),
        sa.Column('block_type', sa.String(), nullable=False),
        sa.Column('execution_order', sa.Integer(), nullable=False),
        sa.Column('decision', sa.String(), nullable=False),
        sa.Column('decision_reason', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('duration_ms', sa.Float(), nullable=True),
        sa.Column('memory_peak_mb', sa.Float(), nullable=True),
        sa.Column('resolved_config', sa.JSON(), nullable=True),
        sa.Column('config_sources', sa.JSON(), nullable=True),
        sa.Column('error_json', sa.JSON(), nullable=True),
        sa.Column('iteration', sa.Integer(), nullable=True),
        sa.Column('loop_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['blueprint_runs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_exec_decision_run_node', 'blueprint_execution_decisions', ['run_id', 'node_id'])
    op.create_index(op.f('ix_blueprint_execution_decisions_run_id'), 'blueprint_execution_decisions', ['run_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_blueprint_execution_decisions_run_id'), table_name='blueprint_execution_decisions')
    op.drop_index('ix_exec_decision_run_node', table_name='blueprint_execution_decisions')
    op.drop_table('blueprint_execution_decisions')
