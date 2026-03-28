"""Merge two 0006 branches into a single head.

Revision ID: 0007_merge
Revises: 0006_artifact_cache, 0006_config_fingerprints
Create Date: 2026-03-28 00:00:00.000000

"""
from typing import Sequence, Union

revision: str = '0007_merge'
down_revision: Union[str, Sequence[str]] = ('0006_artifact_cache', '0006_config_fingerprints')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
