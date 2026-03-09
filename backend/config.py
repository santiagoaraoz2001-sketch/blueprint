import os
from pathlib import Path

# All Specific Labs data lives under ~/.specific-labs/
BASE_DIR = Path(os.environ.get("BLUEPRINT_DATA_DIR", Path.home() / ".specific-labs"))
DB_PATH = BASE_DIR / "specific.db"
MLFLOW_DIR = BASE_DIR / "mlflow"
BLOCKS_DIR = BASE_DIR / "blocks"
CUSTOM_BLOCKS_DIR = BASE_DIR / "custom_blocks"
PIPELINES_DIR = BASE_DIR / "pipelines"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
SNAPSHOTS_DIR = BASE_DIR / "snapshots"

# Built-in blocks shipped with the app
BUILTIN_BLOCKS_DIR = Path(__file__).parent.parent / "blocks"

# Inference server URLs (configurable via environment)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MLX_URL = os.environ.get("MLX_URL", "http://localhost:8080")

DATABASE_URL = f"sqlite:///{DB_PATH}"

# Ensure all directories exist
def ensure_dirs():
    for d in [BASE_DIR, MLFLOW_DIR, BLOCKS_DIR, CUSTOM_BLOCKS_DIR, PIPELINES_DIR, ARTIFACTS_DIR, SNAPSHOTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
