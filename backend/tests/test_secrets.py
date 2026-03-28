"""Tests for the encrypted secrets manager."""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Helpers — redirect all secrets I/O to a temp directory
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_secrets_dir(tmp_path, monkeypatch):
    """Redirect SECRETS_DIR to a fresh temp directory for every test."""
    secrets_dir = tmp_path / ".specific-labs"
    secrets_dir.mkdir()

    import backend.utils.secrets as mod

    monkeypatch.setattr(mod, "SECRETS_DIR", secrets_dir)
    monkeypatch.setattr(mod, "SECRETS_FILE", secrets_dir / "secrets.enc")
    monkeypatch.setattr(mod, "LEGACY_SECRETS_FILE", secrets_dir / "secrets.json")
    monkeypatch.setattr(mod, "LEGACY_MIGRATED_FILE", secrets_dir / "secrets.json.migrated")

    # Use a deterministic passphrase so tests don't depend on keyring
    monkeypatch.setattr(
        mod,
        "_get_or_create_passphrase",
        lambda: "test-passphrase-for-unit-tests",
    )

    yield secrets_dir


# ---------------------------------------------------------------------------
# Core CRUD
# ---------------------------------------------------------------------------


class TestStoreAndRetrieve:
    def test_set_then_get(self):
        from backend.utils.secrets import set_secret, get_secret

        set_secret("MY_KEY", "my-value")
        assert get_secret("MY_KEY") == "my-value"

    def test_overwrite(self):
        from backend.utils.secrets import set_secret, get_secret

        set_secret("KEY", "v1")
        set_secret("KEY", "v2")
        assert get_secret("KEY") == "v2"

    def test_list_returns_sorted_names(self):
        from backend.utils.secrets import set_secret, list_secrets

        set_secret("Z_KEY", "z")
        set_secret("A_KEY", "a")
        assert list_secrets() == ["A_KEY", "Z_KEY"]

    def test_delete(self):
        from backend.utils.secrets import set_secret, get_secret, delete_secret

        set_secret("KEY", "val")
        assert delete_secret("KEY") is True
        assert get_secret("KEY") is None

    def test_delete_nonexistent_returns_false(self):
        from backend.utils.secrets import delete_secret

        assert delete_secret("NOPE") is False


class TestMissingSecret:
    def test_get_missing_returns_none(self):
        from backend.utils.secrets import get_secret

        assert get_secret("DOES_NOT_EXIST") is None

    def test_list_empty(self):
        from backend.utils.secrets import list_secrets

        assert list_secrets() == []


# ---------------------------------------------------------------------------
# Namespace isolation
# ---------------------------------------------------------------------------


class TestNamespaceIsolation:
    def test_different_namespaces_are_independent(self):
        from backend.utils.secrets import set_secret, get_secret, list_secrets

        set_secret("KEY", "value-a", namespace="ns-a")
        set_secret("KEY", "value-b", namespace="ns-b")

        assert get_secret("KEY", namespace="ns-a") == "value-a"
        assert get_secret("KEY", namespace="ns-b") == "value-b"
        assert get_secret("KEY", namespace="default") is None

    def test_list_scoped_to_namespace(self):
        from backend.utils.secrets import set_secret, list_secrets

        set_secret("A", "1", namespace="prod")
        set_secret("B", "2", namespace="dev")

        assert list_secrets(namespace="prod") == ["A"]
        assert list_secrets(namespace="dev") == ["B"]
        assert list_secrets(namespace="default") == []

    def test_delete_scoped_to_namespace(self):
        from backend.utils.secrets import set_secret, get_secret, delete_secret

        set_secret("KEY", "v1", namespace="ns1")
        set_secret("KEY", "v2", namespace="ns2")

        delete_secret("KEY", namespace="ns1")
        assert get_secret("KEY", namespace="ns1") is None
        assert get_secret("KEY", namespace="ns2") == "v2"


# ---------------------------------------------------------------------------
# Legacy plaintext migration
# ---------------------------------------------------------------------------


class TestLegacyMigration:
    def test_migration_encrypts_and_renames(self, _isolated_secrets_dir):
        legacy_path = _isolated_secrets_dir / "secrets.json"
        legacy_path.write_text(json.dumps({
            "OPENAI_KEY": "sk-test-123",
            "HF_TOKEN": "hf-abc-456",
        }))

        from backend.utils.secrets import get_secret, list_secrets

        # First access triggers migration
        assert get_secret("OPENAI_KEY") == "sk-test-123"
        assert get_secret("HF_TOKEN") == "hf-abc-456"
        assert sorted(list_secrets()) == ["HF_TOKEN", "OPENAI_KEY"]

        # Legacy file renamed
        assert not legacy_path.exists()
        assert (_isolated_secrets_dir / "secrets.json.migrated").exists()

        # Encrypted file was created
        enc_path = _isolated_secrets_dir / "secrets.enc"
        assert enc_path.exists()
        # Encrypted file is not plaintext JSON
        raw = enc_path.read_bytes()
        with pytest.raises(json.JSONDecodeError):
            json.loads(raw)

    def test_migration_idempotent(self, _isolated_secrets_dir):
        legacy_path = _isolated_secrets_dir / "secrets.json"
        legacy_path.write_text(json.dumps({"KEY": "value"}))

        from backend.utils.secrets import get_secret

        # First call migrates
        assert get_secret("KEY") == "value"

        # Second call is a no-op (legacy file already renamed)
        assert get_secret("KEY") == "value"

    def test_migration_merges_with_existing_encrypted(self, _isolated_secrets_dir):
        from backend.utils.secrets import set_secret, get_secret

        # Pre-existing encrypted secret
        set_secret("EXISTING", "already-here")

        # Now create a legacy file
        legacy_path = _isolated_secrets_dir / "secrets.json"
        legacy_path.write_text(json.dumps({"NEW_KEY": "new-value"}))

        # Migration should merge, not overwrite
        assert get_secret("NEW_KEY") == "new-value"
        assert get_secret("EXISTING") == "already-here"

    def test_migration_does_not_overwrite_encrypted_secrets(self, _isolated_secrets_dir):
        from backend.utils.secrets import set_secret, get_secret

        # Set a secret in encrypted store
        set_secret("KEY", "encrypted-value")

        # Legacy file has the same key with a different value
        legacy_path = _isolated_secrets_dir / "secrets.json"
        legacy_path.write_text(json.dumps({"KEY": "plaintext-value"}))

        # Encrypted value should win
        assert get_secret("KEY") == "encrypted-value"


# ---------------------------------------------------------------------------
# Encryption verification
# ---------------------------------------------------------------------------


class TestEncryptionAtRest:
    def test_secrets_file_is_not_plaintext(self, _isolated_secrets_dir):
        from backend.utils.secrets import set_secret

        set_secret("SENSITIVE", "super-secret-value-12345")

        enc_path = _isolated_secrets_dir / "secrets.enc"
        raw = enc_path.read_bytes()

        # Must not contain the plaintext value
        assert b"super-secret-value-12345" not in raw
        assert b"SENSITIVE" not in raw

    def test_file_permissions(self, _isolated_secrets_dir):
        from backend.utils.secrets import set_secret

        set_secret("KEY", "val")

        enc_path = _isolated_secrets_dir / "secrets.enc"
        mode = oct(enc_path.stat().st_mode & 0o777)
        assert mode == "0o600"
