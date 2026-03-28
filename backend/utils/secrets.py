"""
Secrets Manager.

Stores secrets encrypted at rest using Fernet symmetric encryption.
The encryption key is derived from a passphrase stored in the OS keychain
(via the ``keyring`` library) with fallback to a machine-specific derivation
using PBKDF2-HMAC with hostname + MAC address as salt.

Secrets are scoped to namespaces (default: 'default'). The encrypted store
lives at ``~/.specific-labs/secrets.enc``.

Legacy plaintext ``secrets.json`` files are automatically migrated on first
access.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
import uuid as _uuid_mod
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("blueprint.secrets")

SECRETS_DIR = Path.home() / ".specific-labs"
SECRETS_FILE = SECRETS_DIR / "secrets.enc"
LEGACY_SECRETS_FILE = SECRETS_DIR / "secrets.json"
LEGACY_MIGRATED_FILE = SECRETS_DIR / "secrets.json.migrated"

_KEYRING_SERVICE = "specific-labs-blueprint"
_KEYRING_USERNAME = "encryption-passphrase"
_PBKDF2_ITERATIONS = 600_000


# ---------------------------------------------------------------------------
# Encryption key derivation
# ---------------------------------------------------------------------------

def _get_machine_salt() -> bytes:
    """Derive a stable salt from hostname + MAC address."""
    hostname = platform.node() or "localhost"
    mac = _uuid_mod.getnode()
    return f"{hostname}-{mac}".encode()


def _derive_key_from_passphrase(passphrase: str) -> bytes:
    """Derive a Fernet key from a passphrase using PBKDF2-HMAC-SHA256."""
    salt = _get_machine_salt()
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode(),
        salt,
        _PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(dk)


def _get_or_create_passphrase() -> str:
    """Retrieve the encryption passphrase from the OS keychain.

    Falls back to a deterministic machine-specific passphrase when keyring is
    not available (e.g. headless servers, CI).
    """
    try:
        import keyring as _keyring

        passphrase = _keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
        if passphrase:
            return passphrase

        # Generate and store a new random passphrase
        passphrase = base64.urlsafe_b64encode(os.urandom(32)).decode()
        _keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, passphrase)
        logger.info("Generated new encryption passphrase and stored in OS keychain")
        return passphrase

    except Exception:
        # Keyring unavailable — fall back to machine-specific derivation
        logger.debug("OS keychain unavailable; using machine-specific key derivation")
        salt = _get_machine_salt()
        return base64.urlsafe_b64encode(salt).decode()


def _get_fernet() -> Fernet:
    """Return a Fernet instance backed by the current encryption key."""
    passphrase = _get_or_create_passphrase()
    key = _derive_key_from_passphrase(passphrase)
    return Fernet(key)


# ---------------------------------------------------------------------------
# Encrypted store I/O
# ---------------------------------------------------------------------------

def _ensure_secrets_dir() -> None:
    """Create the secrets directory if it doesn't exist."""
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)


def _read_store() -> dict[str, dict[str, str]]:
    """Read and decrypt the secrets store.

    Returns a dict of ``{namespace: {name: value}}``.
    """
    _ensure_secrets_dir()

    if not SECRETS_FILE.exists():
        return {}

    try:
        encrypted = SECRETS_FILE.read_bytes()
        if not encrypted:
            return {}
        fernet = _get_fernet()
        decrypted = fernet.decrypt(encrypted)
        data = json.loads(decrypted)
        if not isinstance(data, dict):
            return {}
        return data
    except (InvalidToken, json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read secrets store: %s", type(exc).__name__)
        return {}


def _write_store(store: dict[str, dict[str, str]]) -> None:
    """Encrypt and write the secrets store to disk."""
    _ensure_secrets_dir()
    fernet = _get_fernet()
    payload = json.dumps(store, separators=(",", ":")).encode()
    encrypted = fernet.encrypt(payload)
    SECRETS_FILE.write_bytes(encrypted)
    os.chmod(SECRETS_FILE, 0o600)


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------

def _migrate_legacy_if_needed() -> None:
    """Migrate plaintext secrets.json to encrypted storage.

    Idempotent: safe to call multiple times. If the legacy file has already
    been migrated (renamed to secrets.json.migrated), this is a no-op.
    """
    if not LEGACY_SECRETS_FILE.exists():
        return

    logger.info("Detected legacy plaintext secrets.json — migrating to encrypted storage")

    try:
        raw = LEGACY_SECRETS_FILE.read_text()
        legacy_data = json.loads(raw)
        if not isinstance(legacy_data, dict):
            logger.warning("Legacy secrets.json is not a dict — skipping migration")
            return
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Cannot read legacy secrets.json: %s", exc)
        return

    # Merge into existing store (in case of partial prior migration)
    store = _read_store()
    ns = store.setdefault("default", {})
    migrated_count = 0
    for name, value in legacy_data.items():
        if isinstance(value, str) and name not in ns:
            ns[name] = value
            migrated_count += 1

    _write_store(store)

    # Rename legacy file as backup
    try:
        LEGACY_SECRETS_FILE.rename(LEGACY_MIGRATED_FILE)
    except OSError as exc:
        logger.warning("Could not rename legacy secrets file: %s", exc)

    logger.info("Migrated %d secret(s) from plaintext to encrypted storage", migrated_count)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_secret(name: str, namespace: str = "default") -> str | None:
    """Retrieve a secret by name and namespace. Returns None if not found."""
    _migrate_legacy_if_needed()
    store = _read_store()
    ns = store.get(namespace, {})
    return ns.get(name)


def set_secret(name: str, value: str, namespace: str = "default") -> None:
    """Store a secret. Overwrites if it already exists."""
    _migrate_legacy_if_needed()
    store = _read_store()
    ns = store.setdefault(namespace, {})
    ns[name] = value
    _write_store(store)


def delete_secret(name: str, namespace: str = "default") -> bool:
    """Delete a secret by name. Returns True if it existed."""
    _migrate_legacy_if_needed()
    store = _read_store()
    ns = store.get(namespace, {})
    if name in ns:
        del ns[name]
        # Remove empty namespaces
        if not ns:
            del store[namespace]
        _write_store(store)
        return True
    return False


def list_secrets(namespace: str = "default") -> list[str]:
    """Return a list of all secret names (not values) in a namespace."""
    _migrate_legacy_if_needed()
    store = _read_store()
    ns = store.get(namespace, {})
    return sorted(ns.keys())
