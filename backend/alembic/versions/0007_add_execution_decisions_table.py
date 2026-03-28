"""Extend execution_decisions table with replay inspector columns.

Adds block_type, execution_order, decision_reason, status, timing,
memory, config, error, and loop fields needed by the replay inspector
and support bundle system.

Revision ID: 0007_replay_inspector
Revises: 0007_exec_decisions
Create Date: 2026-03-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0007_replay_inspector'
down_revision: Union[str, Sequence[str]] = '0007_exec_decisions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('execution_decisions') as batch_op:
        batch_op.add_column(sa.Column('block_type', sa.String(), nullable=True, server_default=''))
        batch_op.add_column(sa.Column('execution_order', sa.Integer(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('decision_reason', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('status', sa.String(), nullable=True, server_default='pending'))
        batch_op.add_column(sa.Column('started_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('duration_ms', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('memory_peak_mb', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('resolved_config', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('config_sources', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('error_json', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('iteration', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('loop_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('execution_decisions') as batch_op:
        batch_op.drop_column('created_at')
        batch_op.drop_column('loop_id')
        batch_op.drop_column('iteration')
        batch_op.drop_column('error_json')
        batch_op.drop_column('config_sources')
        batch_op.drop_column('resolved_config')
        batch_op.drop_column('memory_peak_mb')
        batch_op.drop_column('duration_ms')
        batch_op.drop_column('started_at')
        batch_op.drop_column('status')
        batch_op.drop_column('decision_reason')
        batch_op.drop_column('execution_order')
        batch_op.drop_column('block_type')
