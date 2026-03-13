"""add outputs_snapshot to runs

Revision ID: a1b2c3d4e5f6
Revises: 86d04226c57a
Create Date: 2026-03-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '86d04226c57a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add outputs_snapshot column to blueprint_runs."""
    with op.batch_alter_table('blueprint_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('outputs_snapshot', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Remove outputs_snapshot column from blueprint_runs."""
    with op.batch_alter_table('blueprint_runs', schema=None) as batch_op:
        batch_op.drop_column('outputs_snapshot')
