import json as _json
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, Text, JSON, ForeignKey, Index
from ..database import Base


class Artifact(Base):
    """Artifact registry — tracks files produced by block execution."""
    __tablename__ = "blueprint_artifacts"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("blueprint_runs.id"), nullable=False, index=True)
    pipeline_id = Column(String, ForeignKey("blueprint_pipelines.id"), nullable=False, index=True)
    node_id = Column(String, nullable=False)
    block_type = Column(String, nullable=False)

    name = Column(String, nullable=False)
    artifact_type = Column(String, nullable=False, index=True)  # dataset|model|adapter|log|figure|checkpoint|metrics
    file_path = Column(String, nullable=False)
    size_bytes = Column(Integer, default=0)
    hash = Column(String, nullable=True)  # SHA-256

    metadata_ = Column("metadata", JSON, default=dict)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_artifact_pipeline_type", "pipeline_id", "artifact_type"),
    )


class ArtifactRecord(Base):
    """Artifact cache — serialized port-level outputs with SHA-256 verification."""
    __tablename__ = "blueprint_artifact_cache"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("blueprint_runs.id"), nullable=False, index=True)
    node_id = Column(String, nullable=False)
    port_id = Column(String, nullable=False)
    data_type = Column(String, nullable=False)
    serializer = Column(String, nullable=False)       # 'json' | 'text' | 'raw'
    content_hash = Column(String, nullable=False)      # SHA-256 hex
    file_path = Column(String, nullable=False)         # relative to ARTIFACTS_DIR
    size_bytes = Column(Integer, nullable=False)
    preview_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_artifact_cache_run_node", "run_id", "node_id"),
    )

    @classmethod
    def from_manifest(cls, m: "ArtifactManifest") -> "ArtifactRecord":
        from ..engine.artifacts import ArtifactManifest as _AM  # noqa: F811
        return cls(
            id=m.artifact_id,
            run_id=m.run_id,
            node_id=m.node_id,
            port_id=m.port_id,
            data_type=m.data_type,
            serializer=m.serializer,
            content_hash=m.content_hash,
            file_path=m.file_path,
            size_bytes=m.size_bytes,
            preview_json=_json.dumps(m.preview) if m.preview else None,
            created_at=m.created_at,
        )

    def to_manifest(self) -> "ArtifactManifest":
        from ..engine.artifacts import ArtifactManifest
        return ArtifactManifest(
            artifact_id=self.id,
            node_id=self.node_id,
            port_id=self.port_id,
            run_id=self.run_id,
            data_type=self.data_type,
            serializer=self.serializer,
            content_hash=self.content_hash,
            file_path=self.file_path,
            size_bytes=self.size_bytes,
            created_at=self.created_at,
            preview=_json.loads(self.preview_json) if self.preview_json else None,
        )
