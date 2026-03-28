"""
Secrets API Router.

Manages encrypted secrets stored at ~/.specific-labs/secrets.enc.
Only exposes secret names via GET — never returns secret values.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..utils.secrets import get_secret, set_secret, list_secrets, delete_secret

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


class SecretPayload(BaseModel):
    value: str


@router.post("/{name}", status_code=201)
def create_or_update_secret(
    name: str,
    payload: SecretPayload,
    namespace: str = Query("default", description="Secret namespace"),
):
    """Store a secret by name."""
    set_secret(name, payload.value, namespace=namespace)
    return {"status": "ok", "name": name, "namespace": namespace}


@router.get("")
def get_all_secret_names(
    namespace: str = Query("default", description="Secret namespace"),
):
    """List all secret names (NOT values)."""
    names = list_secrets(namespace=namespace)
    return {"secrets": names, "namespace": namespace}


@router.delete("/{name}")
def remove_secret(
    name: str,
    namespace: str = Query("default", description="Secret namespace"),
):
    """Delete a secret by name."""
    deleted = delete_secret(name, namespace=namespace)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Secret '{name}' not found")
    return {"status": "ok", "name": name, "namespace": namespace}
