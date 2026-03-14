"""add blueprint_sweeps table

Revision ID: 0003_add_sweeps
Revises: 0002_data_fingerprints
Create Date: 2026-03-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0003_add_sweeps'
down_revision: Union[str, Sequence[str], None] = '0002_data_fingerprints'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'blueprint_sweeps',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('pipeline_id', sa.String(), sa.ForeignKey('blueprint_pipelines.id'), nullable=False),
        sa.Column('target_node_id', sa.String(), nullable=False),
        sa.Column('metric_name', sa.String(), nullable=False),
        sa.Column('search_type', sa.String(), nullable=False),
        sa.Column('configs', sa.JSON(), nullable=False),
        sa.Column('run_ids', sa.JSON(), default=list),
        sa.Column('results', sa.JSON(), default=list),
        sa.Column('status', sa.String(), default='pending'),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )


def downgrade() -> None:
    op.drop_table('blueprint_sweeps')
