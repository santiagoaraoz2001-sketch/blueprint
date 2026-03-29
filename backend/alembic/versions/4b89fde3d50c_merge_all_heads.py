"""merge_all_heads

Revision ID: 4b89fde3d50c
Revises: 0007_replay_inspector, 0007_experiment_notes, 0007_pipeline_history, 0007_presets, 0007_experiment_variants, 0008_versions_models
Create Date: 2026-03-28 19:42:26.311841

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b89fde3d50c'
down_revision: Union[str, Sequence[str], None] = ('0007_replay_inspector', '0007_experiment_notes', '0007_pipeline_history', '0007_presets', '0007_experiment_variants', '0008_versions_models')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
