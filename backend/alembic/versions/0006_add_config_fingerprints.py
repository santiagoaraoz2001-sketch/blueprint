"""Add config_fingerprints column for Merkle-chain cache fingerprints.

Revision ID: 0006_config_fingerprints
Revises: 0005_run_project_id
Create Date: 2026-03-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0006_config_fingerprints'
down_revision: Union[str, Sequence[str]] = '0005_run_project_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'blueprint_runs',
        sa.Column('config_fingerprints', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('blueprint_runs', 'config_fingerprints')
