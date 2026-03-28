from datetime import datetime, timezone
from sqlalchemy import Column, String, BigInteger, Text, DateTime, JSON, ForeignKey
from ..database import Base


class ModelRecord(Base):
    __tablename__ = "blueprint_model_records"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    version = Column(String, default="1.0.0")  # semver
    format = Column(String, nullable=False)  # 'gguf' | 'safetensors' | 'onnx' | 'pytorch'
    size_bytes = Column(BigInteger, nullable=True)
    source_run_id = Column(String, ForeignKey("blueprint_runs.id"), nullable=True)
    source_node_id = Column(String, nullable=True)
    metrics = Column(JSON, default=dict)  # key:value dict from evaluation results
    tags = Column(String, default="")  # comma-separated tags
    training_config = Column(JSON, default=dict)  # config snapshot from the training block
    source_data = Column(String, nullable=True)  # description of training data used
    model_path = Column(String, nullable=True)  # path to the model file on disk
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
