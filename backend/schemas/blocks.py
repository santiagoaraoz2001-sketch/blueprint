"""Response models for block-related endpoints."""

from pydantic import BaseModel
from typing import Any


class BlockSourceResponse(BaseModel):
    """Returned from the block source endpoint."""
    block: str
    source: str
