#!/usr/bin/env python3
"""
Export OpenAPI schema from the FastAPI app without starting a server.

This script imports the FastAPI app directly and extracts its OpenAPI schema
as JSON. No HTTP server is started — no risk of orphaned processes.

Usage:
    python scripts/generate_api_types.py

Writes: frontend/src/api/schema.json
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
OUTPUT_FILE = PROJECT_ROOT / "frontend" / "src" / "api" / "schema.json"

# Ensure the backend package is importable
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    # Import the FastAPI app — this triggers router registration but does NOT
    # start uvicorn. No background threads, no sockets, no processes to reap.
    from backend.main import app

    schema = app.openapi()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(schema, indent=2, default=str) + "\n")

    # Stats
    paths = schema.get("paths", {})
    endpoint_count = sum(len(methods) for methods in paths.values())
    schema_count = len(schema.get("components", {}).get("schemas", {}))
    print(f"Exported OpenAPI schema to {OUTPUT_FILE}")
    print(f"  {endpoint_count} endpoints, {schema_count} schemas")


if __name__ == "__main__":
    main()
