"""
Secrets API Router.

Manages secrets stored in ~/.specific-labs/secrets.json.
Only exposes secret names via GET — never returns secret values.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..utils.secrets import get_secret, set_secret, list_secrets, delete_secret

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


class SecretPayload(BaseModel):
    value: str


@router.post("/{name}", status_code=201)
def create_or_update_secret(name: str, payload: SecretPayload):
    """Store a secret by name."""
    set_secret(name, payload.value)
    return {"status": "ok", "name": name}


@router.get("")
def get_all_secret_names():
    """List all secret names (NOT values)."""
    names = list_secrets()
    return {"secrets": names}


@router.delete("/{name}")
def remove_secret(name: str):
    """Delete a secret by name."""
    deleted = delete_secret(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Secret '{name}' not found")
    return {"status": "ok", "name": name}
