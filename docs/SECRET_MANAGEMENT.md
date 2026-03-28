# Secret Management

Blueprint stores API keys and other secrets encrypted at rest using Fernet symmetric encryption. Secrets never appear as plaintext on disk.

## How It Works

- **Storage**: Encrypted file at `~/.specific-labs/secrets.enc` (chmod 600)
- **Encryption**: Fernet (AES-128-CBC + HMAC-SHA256) via the `cryptography` library
- **Key derivation**: PBKDF2-HMAC-SHA256 (600,000 iterations) from a passphrase
- **Passphrase storage**: OS keychain (macOS Keychain, GNOME Keyring, Windows Credential Locker) via the `keyring` library, with automatic fallback to a machine-specific derivation for headless environments

## Setting Secrets

### Via API

```bash
# Store a secret (default namespace)
curl -X POST http://localhost:8000/api/secrets/OPENAI_API_KEY \
  -H "Content-Type: application/json" \
  -d '{"value": "sk-..."}'

# Store a secret in a specific namespace
curl -X POST "http://localhost:8000/api/secrets/OPENAI_API_KEY?namespace=production" \
  -H "Content-Type: application/json" \
  -d '{"value": "sk-..."}'
```

### Via Python

```python
from backend.utils.secrets import set_secret

set_secret("OPENAI_API_KEY", "sk-...", namespace="default")
```

## Listing Secrets

```bash
# List secret names (values are never returned)
curl http://localhost:8000/api/secrets

# List secrets in a namespace
curl "http://localhost:8000/api/secrets?namespace=production"
```

## Referencing Secrets in Pipelines

Use `$secret:NAME` in block config fields. Blueprint resolves these at runtime — the actual values are never stored in pipeline definitions or run snapshots.

```yaml
config:
  api_key: "$secret:OPENAI_API_KEY"
```

## Rotating Secrets

Delete the old secret and set the new value:

```bash
curl -X DELETE http://localhost:8000/api/secrets/OPENAI_API_KEY
curl -X POST http://localhost:8000/api/secrets/OPENAI_API_KEY \
  -H "Content-Type: application/json" \
  -d '{"value": "sk-new-key-..."}'
```

## Machine Change / Migration

When moving to a new machine:

1. **If using OS keychain**: Re-enter your secrets on the new machine. The encryption passphrase is stored in the OS keychain and is not transferable.
2. **If using headless fallback**: The key is derived from hostname + MAC address. Secrets must be re-entered if either changes.

## Namespaces

Secrets are scoped to namespaces (default: `"default"`). This allows isolating secrets per environment or project:

```python
set_secret("DB_URL", "postgres://...", namespace="staging")
set_secret("DB_URL", "postgres://...", namespace="production")
```

## Legacy Migration

If you are upgrading from Blueprint < 1.0 where secrets were stored as plaintext JSON at `~/.specific-labs/secrets.json`, the migration is automatic:

1. On first access after upgrade, Blueprint reads the plaintext file
2. All secrets are encrypted and stored in `secrets.enc`
3. The original file is renamed to `secrets.json.migrated` (kept as backup)
4. This process is idempotent — running twice is safe

## Backup Recommendations

- **Back up `~/.specific-labs/secrets.enc`** as part of your regular backup routine
- The encrypted file is useless without the encryption passphrase (stored in your OS keychain)
- On macOS, the passphrase is in Keychain Access under service `specific-labs-blueprint`
- For headless environments, the passphrase is derived from machine identity — no separate backup needed, but secrets must be re-entered on a new machine
