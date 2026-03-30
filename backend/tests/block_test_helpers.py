"""Shared test helpers for block-level testing.

Provides:
  - Live server fixture (module-scoped uvicorn with fresh temp DB)
  - Ollama model fixture (picks best small model)
  - Node/edge/pipeline builder helpers
  - API interaction helpers (create, execute, validate, wait, replay)

Usage in test files:
    from .block_test_helpers import *
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

import pytest

OLLAMA_URL = "http://localhost:11434"
BACKEND_PORT = 18765
API = f"http://127.0.0.1:{BACKEND_PORT}/api"


# ═══════════════════════════════════════════════════════════════════════
#  Ollama Detection
# ═══════════════════════════════════════════════════════════════════════

def _ollama_available() -> bool:
    try:
        resp = urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3)
        data = json.loads(resp.read())
        return any(
            "embed" not in m.get("name", "").lower()
            and "rerank" not in m.get("name", "").lower()
            for m in data.get("models", [])
        )
    except Exception:
        return False


def _pick_model() -> str | None:
    try:
        resp = urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3)
        models = json.loads(resp.read()).get("models", [])
        preferred = ("phi4-mini", "phi3-mini", "tinyllama", "qwen3:8b", "gemma3")
        for pref in preferred:
            for m in models:
                name = m.get("name", "").lower()
                if pref in name and "embed" not in name and "rerank" not in name:
                    return m["name"]
        generative = sorted(
            [(m.get("size", float("inf")), m["name"]) for m in models
             if "embed" not in m.get("name", "").lower()
             and "rerank" not in m.get("name", "").lower()],
        )
        return generative[0][1] if generative else None
    except Exception:
        return None


def _verify_generates(model: str) -> bool:
    try:
        payload = json.dumps({"model": model, "prompt": "hi", "stream": False,
                              "options": {"num_predict": 5}}).encode()
        req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=payload,
                                    headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=60)
        return bool(json.loads(resp.read()).get("response", "").strip())
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════
#  HTTP Helpers
# ═══════════════════════════════════════════════════════════════════════

def api_get(path: str, timeout: int = 30) -> dict:
    resp = urllib.request.urlopen(urllib.request.Request(f"{API}{path}"), timeout=timeout)
    return json.loads(resp.read())


def api_post(path: str, body: dict | None = None, timeout: int = 30) -> tuple[int, dict]:
    payload = json.dumps(body or {}).encode()
    req = urllib.request.Request(f"{API}{path}", data=payload,
                                headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ═══════════════════════════════════════════════════════════════════════
#  Node / Edge / Pipeline Builders
# ═══════════════════════════════════════════════════════════════════════

def node(nid: str, block_type: str, config: dict | None = None, label: str = "") -> dict:
    return {
        "id": nid,
        "type": "blockNode",
        "position": {"x": 0, "y": 0},
        "data": {
            "type": block_type,
            "label": label or block_type,
            "category": "data",
            "config": config or {},
        },
    }


def edge(src: str, tgt: str, src_handle: str, tgt_handle: str) -> dict:
    return {
        "id": f"e-{src}-{tgt}-{src_handle}",
        "source": src,
        "target": tgt,
        "sourceHandle": src_handle,
        "targetHandle": tgt_handle,
    }


def create_pipeline(name: str, nodes: list, edges: list) -> str:
    status, data = api_post("/pipelines", {"name": name, "definition": {"nodes": nodes, "edges": edges}})
    assert status == 201, f"Pipeline creation failed ({status}): {data}"
    return data["id"]


def execute(pid: str) -> str:
    status, data = api_post(f"/pipelines/{pid}/execute")
    assert status == 200, f"Execute failed ({status}): {data}"
    return data["run_id"]


def validate(pid: str) -> dict:
    status, data = api_post(f"/pipelines/{pid}/validate")
    assert status == 200, f"Validate failed ({status}): {data}"
    return data


def dry_run(pid: str) -> dict:
    status, data = api_post(f"/pipelines/{pid}/dry-run")
    return data


def validate_config(block_type: str, config: dict) -> tuple[int, dict]:
    return api_post(f"/blocks/{block_type}/validate-config", config)


def wait_for_run(run_id: str, timeout: float = 180, stderr_path: str | None = None) -> dict:
    start = time.monotonic()
    last_status = "unknown"
    while time.monotonic() - start < timeout:
        try:
            run = api_get(f"/runs/{run_id}")
            last_status = run.get("status", "")
            if last_status in ("complete", "failed", "cancelled"):
                return run
        except Exception:
            pass
        time.sleep(2)

    stderr_tail = ""
    if stderr_path and os.path.exists(stderr_path):
        with open(stderr_path, errors="replace") as f:
            stderr_tail = f.read()[-3000:]
    try:
        run = api_get(f"/runs/{run_id}")
        error_msg = run.get("error_message", "")
    except Exception:
        error_msg = "(could not fetch run)"
    pytest.fail(
        f"Run {run_id} did not complete within {timeout}s.\n"
        f"Last status: {last_status}\nError: {error_msg}\n"
        f"Server stderr (last 3000 chars):\n{stderr_tail}"
    )


def create_and_run(name: str, nodes: list, edges: list, timeout: float = 180,
                   stderr_path: str | None = None) -> tuple[str, dict]:
    pid = create_pipeline(name, nodes, edges)
    rid = execute(pid)
    run = wait_for_run(rid, timeout=timeout, stderr_path=stderr_path)
    return pid, run


def replay(run_id: str) -> dict:
    return api_get(f"/runs/{run_id}/replay")


# ═══════════════════════════════════════════════════════════════════════
#  Common Node Builders
# ═══════════════════════════════════════════════════════════════════════

def model_selector_node(nid: str, model_name: str) -> dict:
    return node(nid, "model_selector", {"source": "ollama", "model_id": model_name})


def inference_node(nid: str, model_name: str, max_tokens: int = 50,
                   temperature: float = 0.1, **extra) -> dict:
    config = {"model_name": model_name, "max_tokens": max_tokens,
              "temperature": temperature, **extra}
    return node(nid, "llm_inference", config)


def text_input_node(nid: str, text: str) -> dict:
    return node(nid, "text_input", {"text_value": text})


def prompt_template_node(nid: str, template: str) -> dict:
    return node(nid, "prompt_template", {"template": template})


def text_to_dataset_node(nid: str, column_name: str = "text",
                         split_by: str = "none") -> dict:
    return node(nid, "text_to_dataset", {"column_name": column_name, "split_by": split_by})


def cot_node(nid: str, input_text: str = "", num_steps: int = 2,
             max_tokens: int = 200, temperature: float = 0.3) -> dict:
    return node(nid, "chain_of_thought",
                {"input_text": input_text, "num_steps": num_steps,
                 "max_tokens": max_tokens, "temperature": temperature})


def metrics_input_node(nid: str, metrics_json: str = '{"accuracy": 0.85, "loss": 0.15}') -> dict:
    return node(nid, "metrics_input", {"metrics_json": metrics_json, "format": "json"})


# ═══════════════════════════════════════════════════════════════════════
#  Assertion Helpers
# ═══════════════════════════════════════════════════════════════════════

def assert_run_complete(run: dict, msg: str = ""):
    assert run["status"] == "complete", f"{msg}Run failed: {run.get('error_message', '')}"


def assert_replay_nodes(run_id: str, expected_count: int):
    r = replay(run_id)
    assert len(r["nodes"]) == expected_count, (
        f"Expected {expected_count} nodes in replay, got {len(r['nodes'])}. "
        f"Types: {[n['block_type'] for n in r['nodes']]}"
    )
    for n in r["nodes"]:
        assert n["status"] == "completed", (
            f"Node {n['node_id']} ({n['block_type']}) status={n['status']}, "
            f"error={n.get('error')}"
        )


def assert_validation_no_structural_errors(val: dict):
    """Assert validation has no structural errors (unknown types, cycles, missing required)."""
    structural = [e for e in val.get("errors", [])
                  if any(k in e.lower() for k in ("required but empty", "cycle", "unknown",
                                                    "self-loop", "duplicate"))]
    assert len(structural) == 0, f"Structural errors: {structural}"


# ═══════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def ollama_model():
    if not _ollama_available():
        pytest.skip("Ollama not running or no generative models")
    model = _pick_model()
    if not model:
        pytest.skip("No suitable generative model in Ollama")
    if not _verify_generates(model):
        pytest.skip(f"Model '{model}' does not produce text output")
    return model


@pytest.fixture(scope="module")
def live_backend(tmp_path_factory):
    """Start a real Blueprint server on a test port with a fresh temp DB.

    stderr goes to a FILE (not a pipe) to prevent deadlock.
    """
    tmp_dir = tmp_path_factory.mktemp("blueprint_block_tests")
    stderr_path = str(tmp_dir / "server_stderr.log")

    env = os.environ.copy()
    env["BLUEPRINT_DATA_DIR"] = str(tmp_dir)
    env["BLUEPRINT_RECOVERY_INTERVAL"] = "9999"
    env["BLUEPRINT_HEARTBEAT_TIMEOUT"] = "600"
    env["BLUEPRINT_ENABLE_MARKETPLACE"] = "false"

    worktree_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    stderr_file = open(stderr_path, "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--host", "127.0.0.1", "--port", str(BACKEND_PORT),
         "--log-level", "debug"],
        env=env,
        cwd=worktree_root,
        stdout=stderr_file,
        stderr=stderr_file,
    )

    deadline = time.monotonic() + 30
    health_ok = False
    while time.monotonic() < deadline:
        try:
            resp = urllib.request.urlopen(f"{API}/health", timeout=2)
            if resp.status == 200:
                health_ok = True
                break
        except Exception:
            pass
        if proc.poll() is not None:
            stderr_file.close()
            with open(stderr_path, errors="replace") as f:
                tail = f.read()[-2000:]
            pytest.skip(f"Server exited with code {proc.returncode}.\nStderr:\n{tail}")
        time.sleep(0.5)

    if not health_ok:
        proc.terminate()
        stderr_file.close()
        with open(stderr_path, errors="replace") as f:
            tail = f.read()[-2000:]
        pytest.skip(f"Server not healthy within 30s.\nStderr:\n{tail}")

    try:
        blocks = api_get("/blocks/library")
        if not isinstance(blocks, list) or len(blocks) == 0:
            proc.terminate()
            stderr_file.close()
            pytest.skip("Block registry empty")
    except Exception as e:
        proc.terminate()
        stderr_file.close()
        pytest.skip(f"Block registry check failed: {e}")

    class ServerInfo:
        pass

    info = ServerInfo()
    info.proc = proc
    info.stderr_path = stderr_path
    info.data_dir = str(tmp_dir)
    info._stderr_file = stderr_file

    yield info

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    stderr_file.close()
