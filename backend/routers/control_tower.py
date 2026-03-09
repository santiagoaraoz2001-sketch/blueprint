from fastapi import APIRouter
from pydantic import BaseModel
from pathlib import Path
from urllib.parse import urlencode
from typing import Optional
import json
import time
import os
import uuid
import httpx

router = APIRouter(prefix="/api/control-tower", tags=["control-tower"])

# Path to shared lock files
SHARED_DIR = Path(os.environ.get("BLUEPRINT_DATA_DIR", Path.home() / ".specific-labs"))

# Default Control Tower port (matches CT's package.json dev script)
DEFAULT_CT_PORT = 4173


@router.get("/status")
def get_status():
    """Check if Control Tower is running by reading its heartbeat file"""
    lock_file = SHARED_DIR / "control-tower.lock"
    if not lock_file.exists():
        return {"connected": False, "message": "Control Tower not detected"}
    try:
        data = json.loads(lock_file.read_text())
        # Check if heartbeat is recent (within 60 seconds)
        if time.time() - data.get("timestamp", 0) > 60:
            return {"connected": False, "message": "Control Tower heartbeat stale"}
        return {"connected": True, "pid": data.get("pid"), "version": data.get("version"), "last_seen": data.get("timestamp")}
    except Exception:
        return {"connected": False, "message": "Invalid heartbeat file"}

@router.post("/heartbeat")
def write_heartbeat():
    """Write Blueprint's heartbeat file"""
    lock_file = SHARED_DIR / "blueprint.lock"
    lock_file.write_text(json.dumps({
        "pid": os.getpid(),
        "timestamp": time.time(),
        "version": "0.1.0",
        "service": "blueprint"
    }))
    return {"status": "ok"}


# ── Multi-instance launch ───────────────────────────────────────────

class InstanceConfig(BaseModel):
    server_url: str             # e.g. "http://localhost:8080"
    model: str                  # e.g. "mlx-community/phi-4-mini-4bit"
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None

class LaunchRequest(BaseModel):
    prompt: str                 # Shared prompt for all instances
    configs: list[InstanceConfig]
    ct_port: int = DEFAULT_CT_PORT
    auto_run: bool = True       # Auto-fire inference on mount

@router.post("/launch")
def launch_control_tower(body: LaunchRequest):
    """Generate Control Tower URLs for multi-instance comparison.

    Blueprint frontend calls this, then opens each URL via window.open().
    Each CT window auto-configures from the query params and (optionally)
    auto-fires the inference.
    """
    run_id = str(uuid.uuid4())
    urls = []

    for cfg in body.configs:
        params: dict[str, str] = {
            "server": cfg.server_url,
            "model": cfg.model,
            "prompt": body.prompt,
            "mode": "subordinate",
            "runId": run_id,
        }
        if body.auto_run:
            params["autoRun"] = "true"
        if cfg.temperature is not None:
            params["temperature"] = str(cfg.temperature)
        if cfg.top_p is not None:
            params["topP"] = str(cfg.top_p)
        if cfg.max_tokens is not None:
            params["maxTokens"] = str(cfg.max_tokens)
        if cfg.system_prompt:
            params["systemPrompt"] = cfg.system_prompt

        url = f"http://localhost:{body.ct_port}?{urlencode(params)}"
        urls.append({"url": url, "model": cfg.model, "server": cfg.server_url})

    return {"urls": urls, "run_id": run_id, "instance_count": len(urls)}


@router.get("/probe")
async def probe_control_tower():
    """Actively probe Control Tower's HTTP health endpoint."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"http://localhost:{DEFAULT_CT_PORT}/api/ct-status")
            if r.status_code == 200:
                data = r.json()
                return {"reachable": True, "port": DEFAULT_CT_PORT, **data}
    except Exception:
        pass
    return {"reachable": False, "port": DEFAULT_CT_PORT}

