"""Inference router — streaming chat, server status, server management."""

import atexit
import json
import logging
import subprocess
import urllib.request
import urllib.error
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import OLLAMA_URL, MLX_URL

logger = logging.getLogger("blueprint.inference")

router = APIRouter(prefix="/api/inference", tags=["inference"])

# ── Tracked spawned server processes ─────────────────────────────────
# Popen objects keyed by server name so they can be killed on shutdown.
_spawned_processes: dict[str, subprocess.Popen] = {}


def shutdown_spawned_servers():
    """Kill all inference servers spawned by this process.

    Called during FastAPI lifespan shutdown and via atexit fallback.
    Uses SIGTERM → SIGKILL escalation to handle stuck Metal/GPU processes.
    """
    for name, proc in list(_spawned_processes.items()):
        if proc.poll() is not None:
            continue  # already dead
        try:
            logger.info("Stopping spawned %s server (PID %d)...", name, proc.pid)
            proc.terminate()  # SIGTERM
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logger.warning("%s PID %d did not stop, sending SIGKILL...", name, proc.pid)
                proc.kill()  # SIGKILL
                proc.wait(timeout=2)
        except Exception as e:
            logger.warning("Failed to stop %s PID %d: %s", name, proc.pid, e)
    _spawned_processes.clear()


# Alias for backward compatibility with upstream code
reap_spawned_processes = shutdown_spawned_servers

atexit.register(shutdown_spawned_servers)


# ── Models ──

class ChatRequest(BaseModel):
    model: str
    backend: str = "ollama"
    messages: list[dict[str, str]]
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = True


class ServerAction(BaseModel):
    pass


# ── Endpoints ──

@router.post("/chat")
async def inference_chat(req: ChatRequest):
    """Stream a chat completion from a local or remote model."""

    if not req.model:
        raise HTTPException(status_code=400, detail="No model specified")

    if req.backend == "ollama":
        return StreamingResponse(
            _stream_ollama(req),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    elif req.backend == "mlx":
        return StreamingResponse(
            _stream_mlx(req),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    elif req.backend == "openai":
        return StreamingResponse(
            _stream_openai(req),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    elif req.backend == "anthropic":
        return StreamingResponse(
            _stream_anthropic(req),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported backend: {req.backend}")


@router.get("/servers")
async def get_servers():
    """Probe local inference servers, detect installed models even when servers are stopped."""
    servers = []

    # ── Ollama ──
    ollama_running = False
    ollama_models: list[str] = []
    ollama_installed = False

    # 1) Check if ollama binary is installed
    try:
        result = subprocess.run(
            ["which", "ollama"], capture_output=True, text=True, timeout=5
        )
        ollama_installed = result.returncode == 0
    except Exception:
        pass

    # 2) Try probing the running server for model list
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                ollama_running = True
                body = json.loads(resp.read().decode("utf-8", errors="ignore"))
                ollama_models = [
                    m.get("name", m.get("model", ""))
                    for m in body.get("models", [])
                    if m.get("name") or m.get("model")
                ]
    except Exception:
        pass

    # 3) If server is NOT running but ollama is installed, use `ollama list` to find downloaded models
    if not ollama_running and ollama_installed:
        try:
            result = subprocess.run(
                ["ollama", "list"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                # Skip header line ("NAME  ID  SIZE  MODIFIED")
                for line in lines[1:]:
                    parts = line.split()
                    if parts:
                        ollama_models.append(parts[0])
        except Exception:
            pass

    servers.append({
        "name": "ollama",
        "running": ollama_running,
        "installed": ollama_installed or ollama_running,
        "url": OLLAMA_URL if ollama_running else None,
        "models": ollama_models,
    })

    # ── MLX ──
    mlx_running = False
    mlx_models: list[str] = []
    mlx_installed = False

    # 1) Check if mlx_lm is installed
    try:
        result = subprocess.run(
            ["python3", "-c", "import mlx_lm; print('ok')"],
            capture_output=True, text=True, timeout=5
        )
        mlx_installed = result.returncode == 0
    except Exception:
        pass

    # 2) Probe running MLX server
    try:
        req = urllib.request.Request(f"{MLX_URL}/v1/models", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                mlx_running = True
                body = json.loads(resp.read().decode("utf-8", errors="ignore"))
                mlx_models = [
                    m.get("id", m.get("name", ""))
                    for m in body.get("data", [])
                    if m.get("id") or m.get("name")
                ]
    except Exception:
        pass

    # 3) If server NOT running, scan local model directories for MLX-compatible models
    if not mlx_running:
        try:
            from ..utils.model_scanner import scan_directories
            local_models = scan_directories()
            for m in local_models:
                name = m["name"]
                path_lower = m["path"].lower()
                # Include safetensors models from mlx-community or with mlx in path
                if ("mlx" in path_lower or "mlx" in name.lower()
                        or m["format"] == "safetensors"):
                    # Convert cache dir name format to model ID
                    if name.startswith("models--"):
                        name = name.replace("models--", "").replace("--", "/")
                    if name not in mlx_models:
                        mlx_models.append(name)
        except Exception:
            pass

    servers.append({
        "name": "mlx",
        "running": mlx_running,
        "installed": mlx_installed or mlx_running,
        "url": MLX_URL if mlx_running else None,
        "models": mlx_models,
    })

    return servers


@router.post("/servers/{name}/start")
async def start_server(name: str):
    """Attempt to start a local inference server."""
    if name == "ollama":
        try:
            proc = subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _spawned_processes["ollama"] = proc
            return {"status": "starting", "name": "ollama", "pid": proc.pid}
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="ollama not found. Install from https://ollama.com")
    elif name == "mlx":
        try:
            proc = subprocess.Popen(
                ["mlx_lm.server", "--port", "8080"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _spawned_processes["mlx"] = proc
            return {"status": "starting", "name": "mlx", "pid": proc.pid}
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="mlx_lm not found. Install with: pip install mlx-lm")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown server: {name}")


# ── Streaming generators ──

async def _stream_ollama(req: ChatRequest):
    """Stream from Ollama's /api/chat endpoint."""
    try:
        payload = json.dumps({
            "model": req.model,
            "messages": req.messages,
            "stream": True,
            "options": {
                "temperature": req.temperature,
                "num_predict": req.max_tokens,
            },
        }).encode("utf-8")

        http_req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(http_req, timeout=120) as resp:
            for line in resp:
                if not line:
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8", errors="ignore"))
                    token = chunk.get("message", {}).get("content", "")
                    done = chunk.get("done", False)
                    if token:
                        yield f"data: {json.dumps({'token': token})}\n\n"
                    if done:
                        yield "data: [DONE]\n\n"
                except (json.JSONDecodeError, ValueError):
                    continue

    except urllib.error.URLError as e:
        yield f"data: {json.dumps({'error': f'Ollama not reachable: {e.reason}'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


async def _stream_mlx(req: ChatRequest):
    """Stream from MLX server (OpenAI-compatible /v1/chat/completions)."""
    try:
        payload = json.dumps({
            "model": req.model,
            "messages": req.messages,
            "stream": True,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
        }).encode("utf-8")

        http_req = urllib.request.Request(
            f"{MLX_URL}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(http_req, timeout=120) as resp:
            for line in resp:
                decoded = line.decode("utf-8", errors="ignore").strip()
                if not decoded or not decoded.startswith("data: "):
                    continue
                data_str = decoded[6:]
                if data_str == "[DONE]":
                    yield "data: [DONE]\n\n"
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        yield f"data: {json.dumps({'token': token})}\n\n"
                except (json.JSONDecodeError, ValueError):
                    continue

    except urllib.error.URLError as e:
        yield f"data: {json.dumps({'error': f'MLX server not reachable: {e.reason}'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


async def _stream_openai(req: ChatRequest):
    """Stream from OpenAI API using the openai SDK."""
    try:
        import openai
        client = openai.OpenAI()

        stream = client.chat.completions.create(
            model=req.model,
            messages=req.messages,  # type: ignore
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield f"data: {json.dumps({'token': delta.content})}\n\n"

        yield "data: [DONE]\n\n"

    except ImportError:
        yield f"data: {json.dumps({'error': 'openai package not installed. pip install openai'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


async def _stream_anthropic(req: ChatRequest):
    """Stream from Anthropic API using the anthropic SDK."""
    try:
        import anthropic
        client = anthropic.Anthropic()

        # Separate system message if present
        system_msg = ""
        messages = []
        for m in req.messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                messages.append(m)

        with client.messages.stream(
            model=req.model,
            messages=messages,  # type: ignore
            system=system_msg or anthropic.NOT_GIVEN,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'token': text})}\n\n"

        yield "data: [DONE]\n\n"

    except ImportError:
        yield f"data: {json.dumps({'error': 'anthropic package not installed. pip install anthropic'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
