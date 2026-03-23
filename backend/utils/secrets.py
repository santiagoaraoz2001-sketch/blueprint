"""
Secrets Manager.

Stores encrypted secrets in ~/.specific-labs/secrets.json with
restricted file permissions (chmod 600).
"""

import json
import os
from pathlib import Path

SECRETS_DIR = Path.home() / ".specific-labs"
SECRETS_FILE = SECRETS_DIR / "secrets.json"


def _ensure_secrets_file() -> Path:
    """Create the secrets directory and file if they don't exist."""
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    if not SECRETS_FILE.exists():
        SECRETS_FILE.write_text("{}")
        os.chmod(SECRETS_FILE, 0o600)
    return SECRETS_FILE


def _read_secrets() -> dict[str, str]:
    """Read secrets from disk."""
    path = _ensure_secrets_file()
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def _write_secrets(secrets: dict[str, str]) -> None:
    """Write secrets to disk with restricted permissions."""
    path = _ensure_secrets_file()
    path.write_text(json.dumps(secrets, indent=2))
    os.chmod(path, 0o600)


def get_secret(name: str) -> str | None:
    """Retrieve a secret by name. Returns None if not found."""
    secrets = _read_secrets()
    return secrets.get(name)


def set_secret(name: str, value: str) -> None:
    """Store a secret. Overwrites if it already exists."""
    secrets = _read_secrets()
    secrets[name] = value
    _write_secrets(secrets)


def list_secrets() -> list[str]:
    """Return a list of all secret names (not values)."""
    secrets = _read_secrets()
    return sorted(secrets.keys())


def delete_secret(name: str) -> bool:
    """Delete a secret by name. Returns True if it existed."""
    secrets = _read_secrets()
    if name in secrets:
        del secrets[name]
        _write_secrets(secrets)
        return True
    return False
