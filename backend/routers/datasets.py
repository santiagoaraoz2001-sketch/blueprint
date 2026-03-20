"""Dataset management — CRUD, preview, file scanning, re-architecture templates."""

from __future__ import annotations

import csv
import json
import logging
import shutil
import sqlite3
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.dataset import Dataset
from ..schemas.dataset import DatasetCreate, DatasetResponse
from ..config import SNAPSHOTS_DIR

_logger = logging.getLogger("blueprint.datasets")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEMPLATE_TIMEOUT_S = 120
_CSV_SNIFF_BYTES = 8192
_SNAPSHOT_TTL_S = 24 * 3600  # 24 hours

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("", response_model=list[DatasetResponse])
def list_datasets(db: Session = Depends(get_db)):
    return db.query(Dataset).order_by(Dataset.created_at.desc()).all()


@router.post("", response_model=DatasetResponse, status_code=201)
def register_dataset(data: DatasetCreate, db: Session = Depends(get_db)):
    dataset = Dataset(id=str(uuid.uuid4()), **data.model_dump())
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


@router.get("/{dataset_id}", response_model=DatasetResponse)
def get_dataset(dataset_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    return dataset


@router.get("/{dataset_id}/preview")
def preview_dataset(
    dataset_id: str,
    rows: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Return preview rows from the dataset file.

    Supports CSV, TSV, JSON, JSONL, Parquet, SQLite, and plain text files.
    """
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")

    source_path = dataset.source_path
    if not source_path or not Path(source_path).is_file():
        return {
            "dataset_id": dataset_id,
            "rows": [],
            "columns": dataset.columns or [],
            "total_rows": dataset.row_count or 0,
            "error": "Source file not found" if source_path else "No source path set",
        }

    ext = Path(source_path).suffix.lower()

    try:
        preview_rows, columns, total_rows = _read_file_preview(
            source_path, ext, rows, offset,
        )
    except Exception as exc:
        _logger.warning("Dataset preview failed for %s: %s", dataset_id, exc)
        return {
            "dataset_id": dataset_id,
            "rows": [],
            "columns": dataset.columns or [],
            "total_rows": dataset.row_count or 0,
            "error": f"Failed to read file: {exc}",
        }

    # Update cached metadata if first-time preview
    if dataset.row_count is None and total_rows > 0:
        dataset.row_count = total_rows
        dataset.column_count = len(columns) if columns else None
        dataset.columns = columns or []
        db.commit()

    return {
        "dataset_id": dataset_id,
        "rows": preview_rows,
        "columns": columns,
        "total_rows": total_rows,
        "offset": offset,
        "format": ext.lstrip("."),
    }


def _read_file_preview(
    file_path: str,
    ext: str,
    max_rows: int,
    offset: int,
) -> tuple[list[dict], list[str], int]:
    """Read preview rows from a file. Returns (rows, columns, total_row_count)."""

    if ext in (".csv", ".tsv"):
        return _read_csv_preview(file_path, max_rows, offset, delimiter="\t" if ext == ".tsv" else ",")

    if ext == ".jsonl":
        return _read_jsonl_preview(file_path, max_rows, offset)

    if ext == ".json":
        return _read_json_preview(file_path, max_rows, offset)

    if ext == ".parquet":
        return _read_parquet_preview(file_path, max_rows, offset)

    if ext in (".db", ".sqlite", ".sqlite3"):
        return _read_sqlite_preview(file_path, max_rows, offset)

    if ext in (".txt", ".md", ".rst", ".log"):
        return _read_text_preview(file_path, max_rows, offset)

    if ext in (".xlsx", ".xls"):
        return _read_excel_preview(file_path, max_rows, offset)

    if ext in (".yaml", ".yml"):
        return _read_yaml_preview(file_path, max_rows, offset)

    # Fallback: try reading as CSV, then as plain text
    try:
        return _read_csv_preview(file_path, max_rows, offset)
    except Exception:
        return _read_text_preview(file_path, max_rows, offset)


def _read_csv_preview(
    file_path: str, max_rows: int, offset: int, delimiter: str = ","
) -> tuple[list[dict], list[str], int]:
    rows: list[dict] = []
    columns: list[str] = []
    total = 0

    with open(file_path, "r", newline="", encoding="utf-8", errors="replace") as f:
        # Sniff up to 8 KB to auto-detect dialect if delimiter isn't forced
        sample = f.read(_CSV_SNIFF_BYTES)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=delimiter + ",;\t|")
        except csv.Error:
            dialect = None

        reader = csv.DictReader(f, dialect=dialect) if dialect else csv.DictReader(f, delimiter=delimiter)
        columns = reader.fieldnames or []

        for i, row in enumerate(reader):
            total = i + 1
            if i < offset:
                continue
            if len(rows) < max_rows:
                rows.append(dict(row))

    return rows, list(columns), total


def _read_jsonl_preview(
    file_path: str, max_rows: int, offset: int
) -> tuple[list[dict], list[str], int]:
    rows: list[dict] = []
    columns_set: dict[str, None] = {}
    total = 0

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            total = i + 1
            if i < offset:
                continue
            if len(rows) < max_rows:
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        rows.append(obj)
                        for k in obj:
                            columns_set[k] = None
                    else:
                        rows.append({"value": obj})
                        columns_set["value"] = None
                except json.JSONDecodeError:
                    rows.append({"_raw": line})
                    columns_set["_raw"] = None

    return rows, list(columns_set.keys()), total


def _read_json_preview(
    file_path: str, max_rows: int, offset: int
) -> tuple[list[dict], list[str], int]:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    if isinstance(data, list):
        total = len(data)
        sliced = data[offset : offset + max_rows]
        rows = [r if isinstance(r, dict) else {"value": r} for r in sliced]
        columns_set: dict[str, None] = {}
        for r in rows:
            for k in r:
                columns_set[k] = None
        return rows, list(columns_set.keys()), total

    if isinstance(data, dict):
        # Could be a single record or a keyed collection
        if all(isinstance(v, list) for v in data.values()):
            # Columnar format → convert to row format
            columns = list(data.keys())
            n = max(len(v) for v in data.values()) if data else 0
            rows = []
            for i in range(offset, min(n, offset + max_rows)):
                row = {col: data[col][i] if i < len(data[col]) else None for col in columns}
                rows.append(row)
            return rows, columns, n
        return [data], list(data.keys()), 1

    return [{"value": data}], ["value"], 1


def _read_parquet_preview(
    file_path: str, max_rows: int, offset: int
) -> tuple[list[dict], list[str], int]:
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise RuntimeError("pyarrow is required to read Parquet files (pip install pyarrow)")

    pf = pq.ParquetFile(file_path)
    total = pf.metadata.num_rows
    columns = [field.name for field in pf.schema_arrow]

    # Read only the needed row group(s) for efficiency
    table = pf.read()
    sliced = table.slice(offset, max_rows)
    rows = sliced.to_pydict()

    # Convert from columnar to row format
    n = sliced.num_rows
    result = []
    for i in range(n):
        row = {col: rows[col][i] for col in columns}
        result.append(row)

    return result, columns, total


def _read_sqlite_preview(
    file_path: str, max_rows: int, offset: int
) -> tuple[list[dict], list[str], int]:
    conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        # Get the first table
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        if not tables:
            return [], [], 0

        table_name = tables[0]["name"]
        # Sanitize table name to prevent SQL injection
        safe_table = table_name.replace('"', '""')
        count_row = conn.execute(f'SELECT COUNT(*) FROM "{safe_table}"').fetchone()
        total = count_row[0] if count_row else 0

        cursor = conn.execute(
            f'SELECT * FROM "{safe_table}" LIMIT ? OFFSET ?',
            (max_rows, offset),
        )
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = [dict(row) for row in cursor.fetchall()]

        return rows, columns, total
    finally:
        conn.close()


def _read_text_preview(
    file_path: str, max_rows: int, offset: int
) -> tuple[list[dict], list[str], int]:
    rows: list[dict] = []
    total = 0
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            total = i + 1
            if i < offset:
                continue
            if len(rows) < max_rows:
                rows.append({"line": i + 1, "text": line.rstrip("\n\r")})
    return rows, ["line", "text"], total


def _read_excel_preview(
    file_path: str, max_rows: int, offset: int
) -> tuple[list[dict], list[str], int]:
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl is required to read Excel files (pip install openpyxl)")

    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    try:
        ws = wb.active
        if ws is None:
            return [], [], 0
        all_rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()

    if not all_rows:
        return [], [], 0

    columns = [str(c) if c is not None else f"col_{i}" for i, c in enumerate(all_rows[0])]
    data_rows = all_rows[1:]  # Skip header row
    total = len(data_rows)

    sliced = data_rows[offset : offset + max_rows]
    rows = []
    for r in sliced:
        row_dict = {}
        for j, val in enumerate(r):
            col_name = columns[j] if j < len(columns) else f"col_{j}"
            row_dict[col_name] = val
        rows.append(row_dict)

    return rows, columns, total


def _read_yaml_preview(
    file_path: str, max_rows: int, offset: int
) -> tuple[list[dict], list[str], int]:
    try:
        import yaml
    except ImportError:
        return _read_text_preview(file_path, max_rows, offset)

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        data = yaml.safe_load(f)

    if isinstance(data, list):
        total = len(data)
        sliced = data[offset : offset + max_rows]
        rows = [r if isinstance(r, dict) else {"value": r} for r in sliced]
        columns_set: dict[str, None] = {}
        for r in rows:
            for k in r:
                columns_set[k] = None
        return rows, list(columns_set.keys()), total

    if isinstance(data, dict):
        return [data], list(data.keys()), 1

    return [{"value": data}], ["value"], 1


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    db.delete(dataset)
    db.commit()


@router.post("/{dataset_id}/snapshots")
def create_snapshot(dataset_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    if not dataset.source_path or not Path(dataset.source_path).exists():
        raise HTTPException(400, "Dataset source file not found")
    
    snapshot_dir = SNAPSHOTS_DIR / dataset_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    snapshot_id = f"snap_{timestamp}"
    original_ext = Path(dataset.source_path).suffix
    snapshot_path = snapshot_dir / f"{snapshot_id}{original_ext}"
    
    shutil.copy2(dataset.source_path, snapshot_path)
    return {"id": snapshot_id, "timestamp": timestamp, "dataset_id": dataset_id}


@router.get("/{dataset_id}/snapshots")
def list_snapshots(dataset_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    
    snapshot_dir = SNAPSHOTS_DIR / dataset_id
    if not snapshot_dir.exists():
        return []
    
    snapshots = []
    # Only keep last 24h of snapshots based on file modification time or name
    cutoff = time.time() - _SNAPSHOT_TTL_S
    
    for file in snapshot_dir.iterdir():
        if not file.is_file() or not file.name.startswith("snap_"):
            continue
        try:
            ts = int(file.stem.replace("snap_", ""))
            # Cleanup old
            if ts < cutoff:
                file.unlink()
                continue
            snapshots.append({
                "id": file.stem,
                "timestamp": ts,
                "dataset_id": dataset_id,
                "size_bytes": file.stat().st_size
            })
        except ValueError:
            pass
            
    return sorted(snapshots, key=lambda x: x["timestamp"], reverse=True)


@router.post("/{dataset_id}/snapshots/{snapshot_id}/restore")
def restore_snapshot(dataset_id: str, snapshot_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    if not dataset.source_path:
        raise HTTPException(400, "Dataset has no source path to restore to")
        
    snapshot_dir = SNAPSHOTS_DIR / dataset_id
    original_ext = Path(dataset.source_path).suffix
    snapshot_path = snapshot_dir / f"{snapshot_id}{original_ext}"

    # Guard against path traversal
    try:
        snapshot_path.resolve().relative_to(snapshot_dir.resolve())
    except ValueError:
        raise HTTPException(400, "Invalid snapshot ID")

    if not snapshot_path.exists():
        raise HTTPException(404, "Snapshot not found")
        
    # Overwrite the current working file with the snapshot
    shutil.copy2(snapshot_path, dataset.source_path)
    # Bump version
    dataset.version = (dataset.version or 1) + 1
    db.commit()
    return {"status": "ok", "restored_version": dataset.version}


# ---------------------------------------------------------------------------
# File scanning — discover data files across the filesystem
# ---------------------------------------------------------------------------

_SCAN_EXTENSIONS = {
    ".csv", ".tsv", ".json", ".jsonl", ".parquet",
    ".db", ".sqlite", ".sqlite3",
    ".xlsx", ".xls",
    ".yaml", ".yml",
    ".txt", ".md", ".log",
}

# Directories to skip during scanning (performance + safety)
_SKIP_DIRS = {
    ".git", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".Trash", ".Spotlight-V100", ".fseventsd", "Library",
    "Applications", "System", ".npm", ".cargo", ".rustup",
}


class ScanRequest(BaseModel):
    directories: list[str] = []
    extensions: list[str] = []
    max_results: int = 500
    max_depth: int = 6
    min_size_bytes: int = 0
    max_size_bytes: int = 0  # 0 = unlimited


class ScannedFile(BaseModel):
    path: str
    name: str
    extension: str
    size_bytes: int
    modified_at: float
    parent_dir: str


@router.post("/scan/discover")
def scan_for_files(req: ScanRequest):
    """Scan directories for data-compatible files.

    If no directories are provided, scans the user's home directory
    (Desktop, Documents, Downloads, and top-level data folders).
    """
    allowed_exts = set(req.extensions) if req.extensions else _SCAN_EXTENSIONS
    # Normalize extensions to include leading dot
    allowed_exts = {e if e.startswith(".") else f".{e}" for e in allowed_exts}

    dirs_to_scan: list[Path] = []
    if req.directories:
        for d in req.directories:
            p = Path(d).expanduser().resolve()
            if p.is_dir():
                dirs_to_scan.append(p)
    else:
        home = Path.home()
        for subdir in ("Desktop", "Documents", "Downloads", "Data", "datasets", "Projects"):
            p = home / subdir
            if p.is_dir():
                dirs_to_scan.append(p)
        # Also scan home root (depth=1 only for top-level files)
        dirs_to_scan.append(home)

    if not dirs_to_scan:
        return {"files": [], "scanned_dirs": [], "error": "No valid directories to scan"}

    results: list[dict] = []
    scanned_dirs: list[str] = [str(d) for d in dirs_to_scan]

    for scan_root in dirs_to_scan:
        if len(results) >= req.max_results:
            break
        _scan_directory(
            scan_root, allowed_exts, results,
            max_results=req.max_results,
            max_depth=req.max_depth,
            min_size=req.min_size_bytes,
            max_size=req.max_size_bytes,
            current_depth=0,
        )

    # Sort by modification time (newest first)
    results.sort(key=lambda f: f["modified_at"], reverse=True)

    return {
        "files": results[:req.max_results],
        "total_found": len(results),
        "scanned_dirs": scanned_dirs,
    }


def _scan_directory(
    directory: Path,
    extensions: set[str],
    results: list[dict],
    max_results: int,
    max_depth: int,
    min_size: int,
    max_size: int,
    current_depth: int,
) -> None:
    """Recursively scan a directory for matching files."""
    if current_depth > max_depth or len(results) >= max_results:
        return

    try:
        entries = list(directory.iterdir())
    except (PermissionError, OSError):
        return

    for entry in entries:
        if len(results) >= max_results:
            return

        try:
            if entry.is_dir():
                if entry.name in _SKIP_DIRS or entry.name.startswith("."):
                    continue
                _scan_directory(
                    entry, extensions, results,
                    max_results, max_depth, min_size, max_size,
                    current_depth + 1,
                )
            elif entry.is_file() and entry.suffix.lower() in extensions:
                stat = entry.stat()
                size = stat.st_size
                if size < min_size:
                    continue
                if max_size > 0 and size > max_size:
                    continue
                results.append({
                    "path": str(entry),
                    "name": entry.name,
                    "extension": entry.suffix.lower(),
                    "size_bytes": size,
                    "modified_at": stat.st_mtime,
                    "parent_dir": str(entry.parent),
                })
        except (PermissionError, OSError):
            continue


@router.post("/scan/register-batch", response_model=list[DatasetResponse])
def register_scanned_files(
    paths: list[str] = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """Register multiple discovered files as datasets in one call."""
    registered = []
    for file_path in paths:
        p = Path(file_path)
        if not p.is_file():
            _logger.warning("Skipping non-existent file: %s", file_path)
            continue

        # Check if already registered
        existing = db.query(Dataset).filter(Dataset.source_path == str(p)).first()
        if existing:
            registered.append(existing)
            continue

        stat = p.stat()
        dataset = Dataset(
            id=str(uuid.uuid4()),
            name=p.stem,
            source="local",
            source_path=str(p),
            description=f"Auto-discovered {p.suffix.lstrip('.')} file",
            size_bytes=stat.st_size,
        )
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        registered.append(dataset)

    return registered


# ---------------------------------------------------------------------------
# Dataset re-architecture templates
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, dict[str, Any]] = {
    "tabular_standard": {
        "name": "Standard Tabular",
        "description": "Flatten nested data into a standard CSV-like table with consistent columns.",
        "supported_inputs": [".json", ".jsonl", ".yaml", ".yml", ".parquet", ".csv", ".tsv"],
        "output_format": ".csv",
        "script": """
import json, csv, sys
from pathlib import Path

def flatten_dict(d, parent_key='', sep='_'):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep).items())
        elif isinstance(v, list):
            items.append((new_key, json.dumps(v)))
        else:
            items.append((new_key, v))
    return dict(items)

input_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])

ext = input_path.suffix.lower()
records = []

if ext in ('.json',):
    data = json.loads(input_path.read_text())
    if isinstance(data, list):
        records = [flatten_dict(r) if isinstance(r, dict) else {'value': r} for r in data]
    elif isinstance(data, dict):
        records = [flatten_dict(data)]
elif ext == '.jsonl':
    for line in input_path.read_text().splitlines():
        if line.strip():
            obj = json.loads(line)
            records.append(flatten_dict(obj) if isinstance(obj, dict) else {'value': obj})
else:
    # CSV/TSV pass-through with flattening
    import csv as _csv
    with open(input_path) as f:
        reader = _csv.DictReader(f)
        records = list(reader)

if records:
    all_keys = list(dict.fromkeys(k for r in records for k in r))
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        writer.writerows(records)
""",
    },
    "ml_train_test": {
        "name": "ML Train/Test Split",
        "description": "Split a tabular dataset into train and test CSV files (80/20 split).",
        "supported_inputs": [".csv", ".tsv", ".json", ".jsonl", ".parquet"],
        "output_format": ".csv",
        "script": """
import csv, json, random, sys
from pathlib import Path

input_path = Path(sys.argv[1])
output_dir = Path(sys.argv[2])
output_dir.mkdir(parents=True, exist_ok=True)

ext = input_path.suffix.lower()
records = []

if ext in ('.csv', '.tsv'):
    delim = '\\t' if ext == '.tsv' else ','
    with open(input_path) as f:
        reader = csv.DictReader(f, delimiter=delim)
        columns = reader.fieldnames or []
        records = list(reader)
elif ext in ('.json',):
    data = json.loads(input_path.read_text())
    records = data if isinstance(data, list) else [data]
    columns = list(dict.fromkeys(k for r in records for k in r)) if records else []
elif ext == '.jsonl':
    for line in input_path.read_text().splitlines():
        if line.strip():
            records.append(json.loads(line))
    columns = list(dict.fromkeys(k for r in records for k in r)) if records else []

random.seed(42)
random.shuffle(records)
split = int(len(records) * 0.8)
train, test = records[:split], records[split:]

for name, subset in [('train.csv', train), ('test.csv', test)]:
    with open(output_dir / name, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(subset)

print(f"Train: {len(train)} rows, Test: {len(test)} rows")
""",
    },
    "jsonl_normalize": {
        "name": "JSONL Normalize",
        "description": "Convert any structured data file into normalized JSONL (one JSON object per line).",
        "supported_inputs": [".json", ".csv", ".tsv", ".yaml", ".yml", ".parquet", ".xlsx"],
        "output_format": ".jsonl",
        "script": """
import json, csv, sys
from pathlib import Path

input_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])

ext = input_path.suffix.lower()
records = []

if ext in ('.csv', '.tsv'):
    delim = '\\t' if ext == '.tsv' else ','
    with open(input_path) as f:
        reader = csv.DictReader(f, delimiter=delim)
        records = list(reader)
elif ext == '.json':
    data = json.loads(input_path.read_text())
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        if all(isinstance(v, list) for v in data.values()):
            keys = list(data.keys())
            n = max(len(v) for v in data.values())
            records = [{k: data[k][i] if i < len(data[k]) else None for k in keys} for i in range(n)]
        else:
            records = [data]
elif ext == '.jsonl':
    for line in input_path.read_text().splitlines():
        if line.strip():
            records.append(json.loads(line))

with open(output_path, 'w') as f:
    for r in records:
        f.write(json.dumps(r, default=str) + '\\n')

print(f"Wrote {len(records)} records")
""",
    },
    "chat_format": {
        "name": "Chat/Instruct Format",
        "description": "Convert tabular data with input/output columns into chat-style JSONL for LLM fine-tuning.",
        "supported_inputs": [".csv", ".tsv", ".json", ".jsonl"],
        "output_format": ".jsonl",
        "script": """
import json, csv, sys
from pathlib import Path

input_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
# Column mapping: auto-detect common column names
INPUT_COLS = {'input', 'question', 'prompt', 'instruction', 'text', 'query', 'source'}
OUTPUT_COLS = {'output', 'answer', 'response', 'completion', 'target', 'label', 'reply'}
SYSTEM_COLS = {'system', 'system_prompt', 'context'}

ext = input_path.suffix.lower()
records = []

if ext in ('.csv', '.tsv'):
    delim = '\\t' if ext == '.tsv' else ','
    with open(input_path) as f:
        records = list(csv.DictReader(f, delimiter=delim))
elif ext == '.json':
    data = json.loads(input_path.read_text())
    records = data if isinstance(data, list) else [data]
elif ext == '.jsonl':
    for line in input_path.read_text().splitlines():
        if line.strip():
            records.append(json.loads(line))

if not records:
    sys.exit("No records found")

cols = set(records[0].keys())
input_col = next((c for c in cols if c.lower() in INPUT_COLS), None)
output_col = next((c for c in cols if c.lower() in OUTPUT_COLS), None)
system_col = next((c for c in cols if c.lower() in SYSTEM_COLS), None)

if not input_col or not output_col:
    # Fallback: use first two columns
    col_list = list(records[0].keys())
    if not col_list:
        sys.exit("Records have no columns")
    input_col = col_list[0]
    output_col = col_list[1] if len(col_list) > 1 else col_list[0]

with open(output_path, 'w') as f:
    for r in records:
        messages = []
        if system_col and r.get(system_col):
            messages.append({"role": "system", "content": str(r[system_col])})
        messages.append({"role": "user", "content": str(r[input_col])})
        messages.append({"role": "assistant", "content": str(r[output_col])})
        f.write(json.dumps({"messages": messages}) + '\\n')

print(f"Converted {len(records)} records to chat format (input={input_col}, output={output_col})")
""",
    },
}


@router.get("/templates/list")
def list_templates():
    """List available dataset re-architecture templates."""
    return [
        {
            "id": tid,
            "name": t["name"],
            "description": t["description"],
            "supported_inputs": t["supported_inputs"],
            "output_format": t["output_format"],
        }
        for tid, t in _TEMPLATES.items()
    ]


class ApplyTemplateRequest(BaseModel):
    template_id: str
    output_path: str = ""  # auto-generated if empty


@router.post("/{dataset_id}/apply-template")
def apply_template(
    dataset_id: str,
    req: ApplyTemplateRequest,
    db: Session = Depends(get_db),
):
    """Apply a re-architecture template to transform a dataset's structure."""
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    if not dataset.source_path or not Path(dataset.source_path).is_file():
        raise HTTPException(400, "Dataset source file not found")

    template = _TEMPLATES.get(req.template_id)
    if not template:
        raise HTTPException(404, f"Template '{req.template_id}' not found")

    src = Path(dataset.source_path)
    if src.suffix.lower() not in template["supported_inputs"]:
        raise HTTPException(
            400,
            f"Template '{template['name']}' does not support {src.suffix} files. "
            f"Supported: {', '.join(template['supported_inputs'])}",
        )

    # Determine output path
    out_ext = template["output_format"]
    if req.output_path:
        output = Path(req.output_path)
    else:
        output = src.parent / f"{src.stem}_{req.template_id}{out_ext}"

    # Execute the template script in an isolated subprocess
    script_content = template["script"]
    tmp_script = Path(tempfile.mktemp(suffix=".py"))
    tmp_script.write_text(script_content)

    try:
        result = subprocess.run(
            ["python3", str(tmp_script), str(src), str(output)],
            capture_output=True,
            text=True,
            timeout=_TEMPLATE_TIMEOUT_S,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise HTTPException(500, f"Template execution failed: {detail}")
    except subprocess.TimeoutExpired:
        raise HTTPException(500, f"Template execution timed out ({_TEMPLATE_TIMEOUT_S}s)")
    finally:
        tmp_script.unlink(missing_ok=True)

    # Register the output as a new dataset
    new_ds = Dataset(
        id=str(uuid.uuid4()),
        name=f"{dataset.name} ({template['name']})",
        source="local",
        source_path=str(output),
        description=f"Generated from '{dataset.name}' using template '{template['name']}'",
        size_bytes=output.stat().st_size if output.is_file() else None,
    )
    db.add(new_ds)
    db.commit()
    db.refresh(new_ds)

    return {
        "status": "ok",
        "output_path": str(output),
        "new_dataset_id": new_ds.id,
        "template": req.template_id,
        "stdout": result.stdout.strip() if result.stdout else "",
    }
