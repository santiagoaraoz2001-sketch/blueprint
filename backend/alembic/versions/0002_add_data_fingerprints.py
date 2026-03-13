"""add data_fingerprints column to blueprint_runs

Revision ID: 0002_data_fingerprints
Revises: 0001_initial
Create Date: 2026-03-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0002_data_fingerprints'
down_revision: Union[str, Sequence[str], None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('blueprint_runs') as batch_op:
        batch_op.add_column(sa.Column('data_fingerprints', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('blueprint_runs') as batch_op:
        batch_op.drop_column('data_fingerprints')
