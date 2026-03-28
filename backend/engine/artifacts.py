"""
Artifact Cache — typed artifact manifests stored as files on disk with SHA-256 verification.

Replaces opaque outputs_snapshot JSON blobs with file-based artifacts that support:
  - Integrity verification via SHA-256 hashes
  - Deterministic serialization (same input → same hash)
  - Typed previews for UI display
  - Disk-based storage under ARTIFACTS_DIR/{run_id}/{node_id}/{port_id}.dat
"""

import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


class ArtifactCorruptionError(Exception):
    """Raised when an artifact's content does not match its stored hash."""


# ── Serializers ──────────────────────────────────────────────────────────

class Serializer(Protocol):
    name: str

    def serialize(self, data: Any) -> bytes: ...
    def deserialize(self, raw: bytes) -> Any: ...


class JsonSerializer:
    name = "json"

    def serialize(self, data: Any) -> bytes:
        return json.dumps(
            data, sort_keys=True, ensure_ascii=False, indent=None
        ).encode("utf-8")

    def deserialize(self, raw: bytes) -> Any:
        return json.loads(raw.decode("utf-8"))


class TextSerializer:
    name = "text"

    def serialize(self, data: Any) -> bytes:
        return str(data).encode("utf-8")

    def deserialize(self, raw: bytes) -> Any:
        return raw.decode("utf-8")


class RawBytesSerializer:
    name = "raw"

    def serialize(self, data: Any) -> bytes:
        if isinstance(data, bytes):
            return data
        if isinstance(data, (bytearray, memoryview)):
            return bytes(data)
        raise TypeError(f"RawBytesSerializer expects bytes, got {type(data).__name__}")

    def deserialize(self, raw: bytes) -> Any:
        return raw


_SERIALIZERS: dict[str, Serializer] = {
    "json": JsonSerializer(),
    "text": TextSerializer(),
    "raw": RawBytesSerializer(),
}


def _pick_serializer(data_type: str) -> Serializer:
    """Choose the appropriate serializer based on data_type."""
    mapping = {
        "text": "text",
        "metrics": "json",
        "config": "json",
        "dataset": "json",
        "model": "json",       # stores reference dict, not weights
        "artifact": "raw",
    }
    name = mapping.get(data_type, "json")
    return _SERIALIZERS[name]


def _make_preview(data: Any, data_type: str) -> dict:
    """Generate a type-appropriate preview dict for UI display."""
    try:
        if data_type == "text":
            s = str(data)
            return {"text": s[:200], "length": len(s)}

        if data_type == "dataset":
            if isinstance(data, dict):
                rows = data.get("rows", data.get("data", []))
                columns = data.get("columns", [])
                if isinstance(rows, list):
                    return {
                        "shape": [len(rows), len(columns) if columns else (len(rows[0]) if rows and isinstance(rows[0], (list, dict)) else 0)],
                        "columns": list(columns)[:20] if columns else [],
                        "sample": rows[:3],
                    }
            if isinstance(data, list):
                cols = list(data[0].keys()) if data and isinstance(data[0], dict) else []
                return {
                    "shape": [len(data), len(cols)],
                    "columns": cols[:20],
                    "sample": data[:3],
                }
            return {"summary": str(data)[:200]}

        if data_type == "metrics":
            if isinstance(data, dict):
                return {"summary": {k: v for k, v in list(data.items())[:20]}}
            return {"summary": str(data)[:200]}

        if data_type == "model":
            if isinstance(data, dict):
                return {
                    "path": str(data.get("path", "")),
                    "size": str(data.get("size_bytes", data.get("size", "unknown"))),
                }
            return {"path": str(data)[:200]}

        # Default: json-ish summary
        return {"summary": str(data)[:200]}
    except Exception:
        return {"error": "preview generation failed"}


# ── Manifest ─────────────────────────────────────────────────────────────

@dataclass
class ArtifactManifest:
    artifact_id: str
    node_id: str
    port_id: str
    run_id: str
    data_type: str
    serializer: str          # 'json' | 'text' | 'raw'
    content_hash: str        # SHA-256 hex
    file_path: str           # relative to base_path
    size_bytes: int
    created_at: datetime
    preview: dict | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "node_id": self.node_id,
            "port_id": self.port_id,
            "run_id": self.run_id,
            "data_type": self.data_type,
            "serializer": self.serializer,
            "content_hash": self.content_hash,
            "file_path": self.file_path,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at.isoformat(),
            "preview": self.preview,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ArtifactManifest":
        created = d["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        return cls(
            artifact_id=d["artifact_id"],
            node_id=d["node_id"],
            port_id=d["port_id"],
            run_id=d["run_id"],
            data_type=d["data_type"],
            serializer=d["serializer"],
            content_hash=d["content_hash"],
            file_path=d["file_path"],
            size_bytes=d["size_bytes"],
            created_at=created,
            preview=d.get("preview"),
            metadata=d.get("metadata", {}),
        )


# ── ArtifactStore ────────────────────────────────────────────────────────

class ArtifactStore:
    """File-based artifact cache with SHA-256 integrity verification."""

    def __init__(self, base_path: Path):
        self.base_path = base_path

    def store(
        self,
        node_id: str,
        port_id: str,
        run_id: str,
        data: Any,
        data_type: str,
    ) -> ArtifactManifest:
        """Serialize data, compute hash, write to disk, return manifest."""
        serializer = _pick_serializer(data_type)
        raw = serializer.serialize(data)
        content_hash = hashlib.sha256(raw).hexdigest()

        # Build path: {base_path}/{run_id}/{node_id}/{port_id}.dat
        rel_path = f"{run_id}/{node_id}/{port_id}.dat"
        abs_path = self.base_path / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(raw)

        # Write manifest sidecar
        preview = _make_preview(data, data_type)
        manifest = ArtifactManifest(
            artifact_id=str(uuid.uuid4()),
            node_id=node_id,
            port_id=port_id,
            run_id=run_id,
            data_type=data_type,
            serializer=serializer.name,
            content_hash=content_hash,
            file_path=rel_path,
            size_bytes=len(raw),
            created_at=datetime.now(timezone.utc),
            preview=preview,
        )

        manifest_path = self.base_path / f"{run_id}/{node_id}/{port_id}.manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return manifest

    def load(self, manifest: ArtifactManifest) -> Any:
        """Read artifact from disk, verify SHA-256, deserialize and return."""
        abs_path = self.base_path / manifest.file_path
        raw = abs_path.read_bytes()

        actual_hash = hashlib.sha256(raw).hexdigest()
        if actual_hash != manifest.content_hash:
            raise ArtifactCorruptionError(
                f"Artifact {manifest.artifact_id} corrupted: "
                f"expected hash {manifest.content_hash}, got {actual_hash}"
            )

        serializer = _SERIALIZERS[manifest.serializer]
        return serializer.deserialize(raw)

    def verify(self, manifest: ArtifactManifest) -> bool:
        """Check whether the on-disk artifact matches its stored hash."""
        abs_path = self.base_path / manifest.file_path
        if not abs_path.exists():
            return False
        try:
            raw = abs_path.read_bytes()
            return hashlib.sha256(raw).hexdigest() == manifest.content_hash
        except OSError:
            return False

    # ── Cleanup ──────────────────────────────────────────────────────

    def cleanup_run(self, run_id: str) -> int:
        """Delete all artifact files for a run. Returns bytes freed."""
        run_dir = self.base_path / run_id
        if not run_dir.is_dir():
            return 0
        bytes_freed = sum(f.stat().st_size for f in run_dir.rglob("*") if f.is_file())
        shutil.rmtree(run_dir)
        return bytes_freed

    def cleanup_older_than(self, days: int) -> int:
        """Delete artifacts older than N days. Returns bytes freed."""
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        bytes_freed = 0

        if not self.base_path.is_dir():
            return 0

        for run_dir in list(self.base_path.iterdir()):
            if not run_dir.is_dir():
                continue
            # Check manifest files for created_at, fall back to mtime
            all_old = True
            for manifest_file in run_dir.rglob("*.manifest.json"):
                try:
                    m = json.loads(manifest_file.read_text(encoding="utf-8"))
                    created = datetime.fromisoformat(m["created_at"]).timestamp()
                    if created > cutoff:
                        all_old = False
                        break
                except (json.JSONDecodeError, KeyError, OSError):
                    if manifest_file.stat().st_mtime > cutoff:
                        all_old = False
                        break

            if all_old:
                bytes_freed += sum(
                    f.stat().st_size for f in run_dir.rglob("*") if f.is_file()
                )
                shutil.rmtree(run_dir)

        return bytes_freed

    def get_storage_usage(self) -> dict:
        """Return storage stats: total_bytes, artifact_count, oldest, newest."""
        if not self.base_path.is_dir():
            return {
                "total_bytes": 0,
                "artifact_count": 0,
                "oldest": None,
                "newest": None,
            }

        total_bytes = 0
        artifact_count = 0
        oldest: datetime | None = None
        newest: datetime | None = None

        for dat_file in self.base_path.rglob("*.dat"):
            total_bytes += dat_file.stat().st_size
            artifact_count += 1

            # Try to read the sidecar manifest for timestamps
            manifest_file = dat_file.with_suffix(".manifest.json")
            ts: datetime | None = None
            if manifest_file.exists():
                try:
                    m = json.loads(manifest_file.read_text(encoding="utf-8"))
                    ts = datetime.fromisoformat(m["created_at"])
                except (json.JSONDecodeError, KeyError, OSError):
                    pass
            if ts is None:
                ts = datetime.fromtimestamp(dat_file.stat().st_mtime, tz=timezone.utc)

            if oldest is None or ts < oldest:
                oldest = ts
            if newest is None or ts > newest:
                newest = ts

        return {
            "total_bytes": total_bytes,
            "artifact_count": artifact_count,
            "oldest": oldest.isoformat() if oldest else None,
            "newest": newest.isoformat() if newest else None,
        }
