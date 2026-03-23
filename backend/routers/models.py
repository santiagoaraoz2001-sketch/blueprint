"""Models router — HuggingFace Hub search and local model detection."""

from __future__ import annotations

import re
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
import asyncio

SAFE_MODEL_ID = re.compile(r'^[a-zA-Z0-9_\-./]+$')

from ..config import OLLAMA_URL
from ..utils.hf_hub import search_models, get_model_details
from ..utils.model_scanner import scan_directories, detect_ollama_models

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/available")
def available_models():
    """Return models grouped by backend for the LLM Inference block config."""
    local = scan_directories()
    result = {'ollama': [], 'gguf': [], 'mlx': [], 'huggingface': []}

    # Detect Ollama models (works even when server is stopped via `ollama list`)
    for m in detect_ollama_models(OLLAMA_URL):
        result['ollama'].append({'name': m['name'], 'size': m['size_bytes']})

    # Try to query running MLX server for its loaded model
    try:
        import urllib.request
        import json as _json
        mlx_resp = urllib.request.urlopen('http://localhost:8080/v1/models', timeout=2)
        mlx_data = _json.loads(mlx_resp.read())
        for m in mlx_data.get('data', []):
            model_id = m.get('id', '')
            if model_id:
                result['mlx'].append({'name': model_id, 'path': '', 'size': 0, 'live': True})
    except Exception:
        pass

    # Categorize scanned local models by format — skip Ollama and MLX duplicates
    live_mlx_ids = {m['name'] for m in result['mlx']}
    for m in local:
        if m['format'] == 'ollama':
            # Already handled above via detect_ollama_models()
            continue
        elif m['format'] == 'gguf':
            result['gguf'].append({'name': m['name'], 'path': m['path'], 'size': m['size_bytes'], 'quant': m.get('detected_quant')})
        elif 'mlx' in m['path'].lower() or 'mlx' in m['name'].lower():
            if m['name'] not in live_mlx_ids:
                result['mlx'].append({'name': m['name'], 'path': m['path'], 'size': m['size_bytes']})
        else:
            result['huggingface'].append({'name': m['name'], 'path': m['path'], 'size': m['size_bytes']})

    return result


@router.get("/search")
def search(
    q: str = Query("", description="Search query"),
    task: str = Query("", description="Pipeline task filter"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
):
    """Search HuggingFace Hub for models."""
    results = search_models(
        query=q,
        task=task if task else None,
        limit=limit,
    )
    return results


@router.get("/details/{model_id:path}")
def details(model_id: str):
    """Get full details for a specific HuggingFace model."""
    if not SAFE_MODEL_ID.match(model_id):
        raise HTTPException(400, "Invalid model ID")
    result = get_model_details(model_id)
    if result is None:
        return {"error": "Model not found or HuggingFace API unavailable"}
    return result


@router.get("/local")
def list_local():
    """List locally detected models from well-known cache directories."""
    return scan_directories()


@router.post("/local/scan")
def trigger_scan():
    """Trigger a fresh scan of local model directories."""
    from ..services.model_discovery import invalidate_cache
    invalidate_cache()
    models = scan_directories()
    return {"count": len(models), "models": models}


@router.get("/ollama/status")
def ollama_status():
    """Check whether the Ollama server is currently running."""
    import urllib.request
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}", timeout=1)
        return {"running": True}
    except Exception:
        return {"running": False}


@router.post("/ollama/start")
def ollama_start():
    """Start the Ollama server if it is not already running."""
    import shutil
    import subprocess
    import time
    import urllib.request

    # Check if already running
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}", timeout=1)
        return {"status": "already_running"}
    except Exception:
        pass

    # Find ollama binary
    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        raise HTTPException(404, "Ollama binary not found on PATH. Install from https://ollama.com")

    # Launch detached process
    try:
        subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise HTTPException(500, f"Failed to start Ollama: {exc}")

    # Poll for readiness (up to 10s)
    for _ in range(20):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"{OLLAMA_URL}", timeout=1)
            # Invalidate discovery cache so next fetch sees running state
            from ..services.model_discovery import invalidate_cache
            invalidate_cache()
            return {"status": "running"}
        except Exception:
            continue

    return {"status": "failed", "error": "Ollama started but did not respond within 10 seconds"}


class InferenceRequest(BaseModel):
    prompt: str = Field(max_length=100000)
    max_tokens: int = Field(default=100, ge=1, le=32768)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)

@router.post("/{model_id:path}/inference")
async def run_inference(model_id: str, req: InferenceRequest):
    if not SAFE_MODEL_ID.match(model_id):
        raise HTTPException(400, "Invalid model ID")
    """Run local inference on a downloaded/trained model."""
    try:
        from transformers import pipeline  # noqa: F401
    except ImportError:
        # Fallback for demo/development if transformers isn't installed
        await asyncio.sleep(1)
        return {
            "text": f"Mock response for '{req.prompt}' from model '{model_id}'.\n\n(Install 'transformers' and 'torch' for actual local inference.)",
            "model_id": model_id
        }

    # If transformers is available, load it (in a real app this would be cached in memory)
    try:
        # For a truly robust app, loading should be backgrounded.
        # This is simplified for demonstration of the "Vibe Check" feature.
        pipe = pipeline("text-generation", model=model_id, max_new_tokens=req.max_tokens)
        result = pipe(req.prompt, num_return_sequences=1, temperature=req.temperature)
        generated_text = result[0]["generated_text"]
        
        # Remove the prompt from the generated text if it's there
        if generated_text.startswith(req.prompt):
            generated_text = generated_text[len(req.prompt):].strip()
            
        return {"text": generated_text, "model_id": model_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {str(e)}")
