"""add metrics_log to runs

Revision ID: a1b2c3d4e5f6
Revises: 86d04226c57a
Create Date: 2026-03-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '86d04226c57a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('blueprint_runs') as batch_op:
        batch_op.add_column(sa.Column('metrics_log', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('blueprint_runs') as batch_op:
        batch_op.drop_column('metrics_log')
