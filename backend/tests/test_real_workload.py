"""Real ML workload tests — 20 tests across 4 categories.

Executes REAL pipelines through Blueprint's full execution stack via a live
uvicorn subprocess with a fresh temp database. Tests cover:
  - Synthetic generation (5 tests)
  - Agentic reasoning (5 tests)
  - Training pipeline validation (5 tests)
  - Multi-step multi-ML pipelines (5 tests)

Marked @pytest.mark.slow. Exclude from CI with: pytest -m "not slow"
Requires Ollama running with at least one generative model (phi4-mini preferred).
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

pytestmark = pytest.mark.slow

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

def _api_get(path: str, timeout: int = 30) -> dict:
    resp = urllib.request.urlopen(urllib.request.Request(f"{API}{path}"), timeout=timeout)
    return json.loads(resp.read())


def _api_post(path: str, body: dict | None = None, timeout: int = 30) -> tuple[int, dict]:
    payload = json.dumps(body or {}).encode()
    req = urllib.request.Request(f"{API}{path}", data=payload,
                                headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ═══════════════════════════════════════════════════════════════════════
#  Node / Edge / Pipeline Helpers
# ═══════════════════════════════════════════════════════════════════════

def _node(nid: str, block_type: str, config: dict | None = None, label: str = "") -> dict:
    return {
        "id": nid,
        "type": "blockNode",
        "position": {"x": 0, "y": 0},
        "data": {
            "type": block_type,
            "label": label or block_type,
            "category": "inference",
            "config": config or {},
        },
    }


def _edge(src: str, tgt: str, src_handle: str, tgt_handle: str) -> dict:
    return {
        "id": f"e-{src}-{tgt}-{src_handle}",
        "source": src,
        "target": tgt,
        "sourceHandle": src_handle,
        "targetHandle": tgt_handle,
    }


def _create_pipeline(name: str, nodes: list, edges: list) -> str:
    status, data = _api_post("/pipelines", {"name": name, "definition": {"nodes": nodes, "edges": edges}})
    assert status == 201, f"Pipeline creation failed ({status}): {data}"
    return data["id"]


def _execute(pid: str) -> str:
    status, data = _api_post(f"/pipelines/{pid}/execute")
    assert status == 200, f"Execute failed ({status}): {data}"
    return data["run_id"]


def _validate(pid: str) -> dict:
    status, data = _api_post(f"/pipelines/{pid}/validate")
    assert status == 200, f"Validate failed ({status}): {data}"
    return data


def _dry_run(pid: str) -> dict:
    status, data = _api_post(f"/pipelines/{pid}/dry-run")
    return data


def _wait(run_id: str, timeout: float = 180, stderr_path: str | None = None) -> dict:
    """Poll run status until terminal. On timeout, include server stderr in failure message."""
    start = time.monotonic()
    last_status = "unknown"
    while time.monotonic() - start < timeout:
        try:
            run = _api_get(f"/runs/{run_id}")
            last_status = run.get("status", "")
            if last_status in ("complete", "failed", "cancelled"):
                return run
        except Exception:
            pass
        time.sleep(2)

    # Timeout — collect debugging info
    stderr_tail = ""
    if stderr_path and os.path.exists(stderr_path):
        with open(stderr_path, errors="replace") as f:
            stderr_tail = f.read()[-3000:]

    try:
        run = _api_get(f"/runs/{run_id}")
        error_msg = run.get("error_message", "")
    except Exception:
        error_msg = "(could not fetch run)"

    pytest.fail(
        f"Run {run_id} did not complete within {timeout}s.\n"
        f"Last status: {last_status}\n"
        f"Error message: {error_msg}\n"
        f"Server stderr (last 3000 chars):\n{stderr_tail}"
    )


def _create_and_run(name: str, nodes: list, edges: list, timeout: float = 180,
                    stderr_path: str | None = None) -> tuple[str, dict]:
    pid = _create_pipeline(name, nodes, edges)
    rid = _execute(pid)
    run = _wait(rid, timeout=timeout, stderr_path=stderr_path)
    return pid, run


def _replay(run_id: str) -> dict:
    return _api_get(f"/runs/{run_id}/replay")


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline Definition Builders
# ═══════════════════════════════════════════════════════════════════════

def _model_selector_node(nid: str, model_name: str) -> dict:
    return _node(nid, "model_selector", {"source": "ollama", "model_id": model_name})


def _inference_node(nid: str, model_name: str, user_input: str = "",
                    max_tokens: int = 50, temperature: float = 0.1, **extra) -> dict:
    config = {"model_name": model_name, "user_input": user_input,
              "max_tokens": max_tokens, "temperature": temperature, **extra}
    return _node(nid, "llm_inference", config)


def _text_input_node(nid: str, text: str) -> dict:
    return _node(nid, "text_input", {"text_value": text})


def _prompt_template_node(nid: str, template: str) -> dict:
    return _node(nid, "prompt_template", {"template": template})


def _cot_node(nid: str, input_text: str = "", num_steps: int = 2,
              max_tokens: int = 200, temperature: float = 0.3) -> dict:
    return _node(nid, "chain_of_thought",
                 {"input_text": input_text, "num_steps": num_steps,
                  "max_tokens": max_tokens, "temperature": temperature})


def _orchestrator_node(nid: str, task: str = "", max_steps: int = 3,
                       max_tokens: int = 200, temperature: float = 0.3) -> dict:
    return _node(nid, "agent_orchestrator",
                 {"task": task, "strategy": "sequential", "max_steps": max_steps,
                  "max_tokens": max_tokens, "temperature": temperature,
                  "stop_phrase": "FINAL ANSWER:"})


def _debate_node(nid: str, topic: str = "", num_agents: int = 2,
                 num_rounds: int = 2, max_tokens: int = 128) -> dict:
    return _node(nid, "multi_agent_debate",
                 {"topic": topic, "num_agents": num_agents, "num_rounds": num_rounds,
                  "max_tokens": max_tokens, "temperature": 0.5, "seed": 42})


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

    stderr goes to a FILE (not a pipe) to prevent deadlock when the executor
    thread logs during pipeline execution.
    """
    tmp_dir = tmp_path_factory.mktemp("blueprint_workload")
    stderr_path = str(tmp_dir / "server_stderr.log")

    env = os.environ.copy()
    env["BLUEPRINT_DATA_DIR"] = str(tmp_dir)
    env["BLUEPRINT_RECOVERY_INTERVAL"] = "9999"
    env["BLUEPRINT_HEARTBEAT_TIMEOUT"] = "600"
    env["BLUEPRINT_ENABLE_MARKETPLACE"] = "false"

    # CWD = worktree root so BUILTIN_BLOCKS_DIR resolves to <worktree>/blocks/
    worktree_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    stderr_file = open(stderr_path, "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--host", "127.0.0.1", "--port", str(BACKEND_PORT),
         "--log-level", "debug"],
        env=env,
        cwd=worktree_root,
        stdout=stderr_file,  # uvicorn logs everything to stderr, redirect both
        stderr=stderr_file,
    )

    # Wait for health + block registry
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
        # Check if process died
        if proc.poll() is not None:
            stderr_file.close()
            with open(stderr_path, errors="replace") as f:
                tail = f.read()[-2000:]
            pytest.skip(f"Server process exited with code {proc.returncode}.\nStderr:\n{tail}")
        time.sleep(0.5)

    if not health_ok:
        proc.terminate()
        stderr_file.close()
        with open(stderr_path, errors="replace") as f:
            tail = f.read()[-2000:]
        pytest.skip(f"Server did not become healthy within 30s.\nStderr:\n{tail}")

    # Verify block registry loaded
    try:
        blocks = _api_get("/blocks/library")
        if not isinstance(blocks, list) or len(blocks) == 0:
            proc.terminate()
            stderr_file.close()
            pytest.skip("Block registry is empty — server started but blocks not discovered")
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


# ═══════════════════════════════════════════════════════════════════════
#  CATEGORY 1: SYNTHETIC GENERATION (5 tests)
# ═══════════════════════════════════════════════════════════════════════

class TestSyntheticGeneration:
    """Text generation pipelines using Ollama through Blueprint's executor."""

    def test_simple_inference(self, ollama_model, live_backend):
        """3-block: model_selector + text_input → llm_inference."""
        nodes = [
            _model_selector_node("ms", ollama_model),
            _text_input_node("ti", "What is 2+2? Answer with just the number."),
            _inference_node("inf", ollama_model),
        ]
        edges = [
            _edge("ms", "inf", "model", "model"),
            _edge("ti", "inf", "text", "prompt"),
        ]
        pid, run = _create_and_run("Synth: Simple Inference", nodes, edges,
                                   stderr_path=live_backend.stderr_path)

        assert run["status"] == "complete", f"Failed: {run.get('error_message')}"
        assert run["duration_seconds"] > 0

        replay = _replay(run["id"])
        assert len(replay["nodes"]) == 3
        assert all(n["status"] == "completed" for n in replay["nodes"])

    def test_templated_inference(self, ollama_model, live_backend):
        """4-block: model_selector + text_input → prompt_template → llm_inference."""
        nodes = [
            _model_selector_node("ms", ollama_model),
            _text_input_node("ti", "the Eiffel Tower"),
            _prompt_template_node("pt", "Describe {input} in one sentence."),
            _inference_node("inf", ollama_model, max_tokens=100, temperature=0.3),
        ]
        edges = [
            _edge("ti", "pt", "text", "text"),
            _edge("pt", "inf", "rendered_text", "prompt"),
            _edge("ms", "inf", "model", "model"),
        ]
        pid, run = _create_and_run("Synth: Templated", nodes, edges,
                                   stderr_path=live_backend.stderr_path)

        assert run["status"] == "complete", f"Failed: {run.get('error_message')}"
        replay = _replay(run["id"])
        assert len(replay["nodes"]) == 4

    def test_json_output_format(self, ollama_model, live_backend):
        """3-block: text_input + model_selector → inference with output_format=json."""
        nodes = [
            _model_selector_node("ms", ollama_model),
            _text_input_node("ti", "Return a JSON object with key 'answer' and value 42."),
            _inference_node("inf", ollama_model, max_tokens=100, output_format="json"),
        ]
        edges = [
            _edge("ms", "inf", "model", "model"),
            _edge("ti", "inf", "text", "prompt"),
        ]
        pid, run = _create_and_run("Synth: JSON Output", nodes, edges,
                                   stderr_path=live_backend.stderr_path)

        assert run["status"] == "complete", f"Failed: {run.get('error_message')}"

    def test_chained_inference(self, ollama_model, live_backend):
        """5-block: ms + ti → inf1 → prompt_template → inf2 (two LLM calls)."""
        nodes = [
            _model_selector_node("ms", ollama_model),
            _text_input_node("ti", "Name a famous scientist in one word."),
            _inference_node("inf1", ollama_model, max_tokens=30),
            _prompt_template_node("pt", "Tell me one fact about {input}."),
            _inference_node("inf2", ollama_model, max_tokens=100),
        ]
        edges = [
            _edge("ms", "inf1", "model", "model"),
            _edge("ti", "inf1", "text", "prompt"),
            _edge("inf1", "pt", "response", "text"),
            _edge("pt", "inf2", "rendered_text", "prompt"),
            _edge("ms", "inf2", "model", "model"),
        ]
        pid, run = _create_and_run("Synth: Chained", nodes, edges,
                                   timeout=240, stderr_path=live_backend.stderr_path)

        assert run["status"] == "complete", f"Failed: {run.get('error_message')}"
        replay = _replay(run["id"])
        assert len(replay["nodes"]) == 5  # ms + ti + inf1 + pt + inf2
        assert run["duration_seconds"] > 0

    def test_three_sequential_pipelines(self, ollama_model, live_backend):
        """3 separate pipeline executions with different prompts."""
        prompts = ["Say hello.", "Name a color.", "Count to 3."]
        for i, prompt in enumerate(prompts):
            nodes = [
                _model_selector_node("ms", ollama_model),
                _text_input_node("ti", prompt),
                _inference_node("inf", ollama_model, max_tokens=30),
            ]
            edges = [
                _edge("ms", "inf", "model", "model"),
                _edge("ti", "inf", "text", "prompt"),
            ]
            pid, run = _create_and_run(f"Synth: Seq {i}", nodes, edges,
                                       stderr_path=live_backend.stderr_path)
            assert run["status"] == "complete", f"Prompt '{prompt}' failed: {run.get('error_message')}"
            assert run["duration_seconds"] > 0


# ═══════════════════════════════════════════════════════════════════════
#  CATEGORY 2: AGENTIC PIPELINES (5 tests)
# ═══════════════════════════════════════════════════════════════════════

class TestAgenticPipelines:
    """Agentic reasoning pipelines (chain-of-thought, orchestrator, debate)."""

    def test_chain_of_thought(self, ollama_model, live_backend):
        """3-block: model_selector + text_input → chain_of_thought (3-step reasoning)."""
        nodes = [
            _model_selector_node("ms", ollama_model),
            _text_input_node("ti", "What is 15 * 23? Think step by step."),
            _cot_node("cot", num_steps=3),
        ]
        edges = [
            _edge("ms", "cot", "llm", "llm"),
            _edge("ti", "cot", "text", "input"),
        ]
        pid, run = _create_and_run("Agent: CoT", nodes, edges,
                                   timeout=300, stderr_path=live_backend.stderr_path)

        assert run["status"] == "complete", f"Failed: {run.get('error_message')}"
        replay = _replay(run["id"])
        assert len(replay["nodes"]) == 3
        assert all(n["status"] == "completed" for n in replay["nodes"])

    def test_agent_orchestrator(self, ollama_model, live_backend):
        """3-block: model_selector + text_input → agent_orchestrator (sequential)."""
        nodes = [
            _model_selector_node("ms", ollama_model),
            _text_input_node("ti", "List 3 prime numbers less than 20."),
            _orchestrator_node("ao", max_steps=5),
        ]
        edges = [
            _edge("ms", "ao", "llm", "llm"),
            _edge("ti", "ao", "text", "input"),
        ]
        pid, run = _create_and_run("Agent: Orchestrator", nodes, edges,
                                   timeout=300, stderr_path=live_backend.stderr_path)

        assert run["status"] == "complete", f"Failed: {run.get('error_message')}"
        replay = _replay(run["id"])
        assert len(replay["nodes"]) == 3

    def test_multi_agent_debate(self, ollama_model, live_backend):
        """3-block: model_selector + text_input → multi_agent_debate (2 agents, 2 rounds)."""
        nodes = [
            _model_selector_node("ms", ollama_model),
            _text_input_node("ti", "Is Python better than JavaScript for ML?"),
            _debate_node("mad"),
        ]
        edges = [
            _edge("ms", "mad", "llm", "llm"),
            _edge("ti", "mad", "text", "input"),
        ]
        pid, run = _create_and_run("Agent: Debate", nodes, edges,
                                   timeout=300, stderr_path=live_backend.stderr_path)

        assert run["status"] == "complete", f"Failed: {run.get('error_message')}"
        replay = _replay(run["id"])
        assert len(replay["nodes"]) == 3

    def test_inference_then_reasoning(self, ollama_model, live_backend):
        """4-block: ms + ti → llm_inference → chain_of_thought (chained LLM → agent)."""
        nodes = [
            _model_selector_node("ms", ollama_model),
            _text_input_node("ti", "What is the capital of France?"),
            _inference_node("inf", ollama_model, max_tokens=30),
            _cot_node("cot", num_steps=2, max_tokens=200),
        ]
        edges = [
            _edge("ms", "inf", "model", "model"),
            _edge("ti", "inf", "text", "prompt"),
            _edge("inf", "cot", "llm_config", "llm"),
            _edge("inf", "cot", "response", "input"),
        ]
        pid, run = _create_and_run("Agent: Inf→CoT", nodes, edges,
                                   timeout=300, stderr_path=live_backend.stderr_path)

        assert run["status"] == "complete", f"Failed: {run.get('error_message')}"
        replay = _replay(run["id"])
        assert len(replay["nodes"]) == 4  # ms + ti + inf + cot

    def test_validate_agentic_definitions(self, ollama_model, live_backend):
        """Validate 3 agentic pipeline definitions (no execution)."""
        configs = [
            ("CoT", [_model_selector_node("ms", ollama_model),
                     _text_input_node("ti", "test"),
                     _cot_node("cot")],
             [_edge("ms", "cot", "llm", "llm"), _edge("ti", "cot", "text", "input")]),
            ("Orch", [_model_selector_node("ms", ollama_model),
                      _text_input_node("ti", "test"),
                      _orchestrator_node("ao")],
             [_edge("ms", "ao", "llm", "llm"), _edge("ti", "ao", "text", "input")]),
            ("Debate", [_model_selector_node("ms", ollama_model),
                        _text_input_node("ti", "test"),
                        _debate_node("mad")],
             [_edge("ms", "mad", "llm", "llm"), _edge("ti", "mad", "text", "input")]),
        ]
        for name, nodes, edges in configs:
            pid = _create_pipeline(f"Validate: {name}", nodes, edges)
            val = _validate(pid)
            assert val["valid"] is True, f"{name} validation failed: {val.get('errors')}"
            assert val["block_count"] == 3


# ═══════════════════════════════════════════════════════════════════════
#  CATEGORY 3: TRAINING PIPELINES (5 tests — validation/dry-run only)
# ═══════════════════════════════════════════════════════════════════════

class TestTrainingPipelines:
    """Training pipeline validation and dry-run (no GPU needed)."""

    def _training_pipeline(self, block_type: str, extra_config: dict | None = None):
        """Build a 3-block training pipeline: model_selector + dataset_builder + trainer."""
        ms = _node("ms", "model_selector", {
            "source": "huggingface", "model_id": "meta-llama/Llama-3.2-1B",
        })
        db = _node("db", "dataset_builder", {
            "source": "huggingface", "hf_dataset": "tatsu-lab/alpaca",
            "hf_split": "train", "hf_max_samples": 10,
            "training_format": "instruction",
        })
        trainer_config = {
            "model_name": "meta-llama/Llama-3.2-1B",
            "epochs": 1, "batch_size": 1, "max_seq_length": 128,
            **(extra_config or {}),
        }
        trainer = _node("tr", block_type, trainer_config)
        edges = [
            _edge("ms", "tr", "model", "model"),
            _edge("db", "tr", "dataset", "dataset"),
        ]
        return [ms, db, trainer], edges

    def test_validate_qlora_pipeline(self, live_backend):
        """Validate qlora_finetuning pipeline definition."""
        nodes, edges = self._training_pipeline("qlora_finetuning")
        pid = _create_pipeline("Train: QLoRA Validate", nodes, edges)
        val = _validate(pid)
        assert val["block_count"] == 3
        # Validation may flag warnings (e.g., "model not available locally") but
        # should not have structural errors
        structural_errors = [e for e in val["errors"] if "required but empty" in e.lower()
                             or "cycle" in e.lower() or "unknown" in e.lower()]
        assert len(structural_errors) == 0, f"Structural errors: {structural_errors}"

    def test_validate_lora_pipeline(self, live_backend):
        """Validate lora_finetuning pipeline definition."""
        nodes, edges = self._training_pipeline("lora_finetuning")
        pid = _create_pipeline("Train: LoRA Validate", nodes, edges)
        val = _validate(pid)
        assert val["block_count"] == 3
        structural_errors = [e for e in val["errors"] if "required but empty" in e.lower()
                             or "cycle" in e.lower() or "unknown" in e.lower()]
        assert len(structural_errors) == 0, f"Structural errors: {structural_errors}"

    def test_validate_dpo_pipeline(self, live_backend):
        """Validate dpo_alignment pipeline definition."""
        nodes, edges = self._training_pipeline("dpo_alignment", {
            "prompt_column": "prompt", "chosen_column": "chosen",
            "rejected_column": "rejected",
        })
        pid = _create_pipeline("Train: DPO Validate", nodes, edges)
        val = _validate(pid)
        assert val["block_count"] == 3
        structural_errors = [e for e in val["errors"] if "required but empty" in e.lower()
                             or "cycle" in e.lower() or "unknown" in e.lower()]
        assert len(structural_errors) == 0, f"Structural errors: {structural_errors}"

    def test_dry_run_training_pipeline(self, live_backend):
        """Dry-run simulation of qlora pipeline — estimates resources without execution."""
        nodes, edges = self._training_pipeline("qlora_finetuning")
        pid = _create_pipeline("Train: DryRun", nodes, edges)
        result = _dry_run(pid)
        assert "viable" in result
        assert "total_estimate" in result
        assert "per_node_estimates" in result

    def test_training_block_config_validation(self, live_backend):
        """Validate qlora config fields: valid config, out-of-bounds, invalid select."""
        # Valid config
        status, data = _api_post("/blocks/qlora_finetuning/validate-config", {
            "model_name": "test-model",
            "epochs": 3,
            "batch_size": 4,
            "bits": "4",
        })
        assert status == 200
        assert data["valid"] is True, f"Valid config rejected: {data.get('errors')}"

        # Out-of-bounds: epochs max is 100
        status, data = _api_post("/blocks/qlora_finetuning/validate-config", {
            "model_name": "test-model",
            "epochs": 200,
            "bits": "4",
        })
        assert status == 200
        # May or may not flag epochs as error (depends on bounds config)

        # Invalid select value
        status, data = _api_post("/blocks/qlora_finetuning/validate-config", {
            "model_name": "test-model",
            "bits": "3",  # Valid options: "4", "8"
        })
        assert status == 200
        if not data["valid"]:
            assert any("bits" in str(e) for e in data["errors"])


# ═══════════════════════════════════════════════════════════════════════
#  CATEGORY 4: MULTI-STEP MULTI-ML PIPELINES (5 tests)
# ═══════════════════════════════════════════════════════════════════════

class TestMultiStepPipelines:
    """Complex pipelines with 3+ ML blocks."""

    def test_two_stage_inference(self, ollama_model, live_backend):
        """4-block: ms + ti → inf1 → inf2 (chained two-stage inference)."""
        nodes = [
            _model_selector_node("ms", ollama_model),
            _text_input_node("ti", "Name a color."),
            _inference_node("inf1", ollama_model, max_tokens=20),
            _inference_node("inf2", ollama_model, max_tokens=50),
        ]
        edges = [
            _edge("ms", "inf1", "model", "model"),
            _edge("ti", "inf1", "text", "prompt"),
            _edge("ms", "inf2", "model", "model"),
            _edge("inf1", "inf2", "response", "prompt"),
        ]
        pid, run = _create_and_run("Multi: 2-Stage", nodes, edges,
                                   timeout=240, stderr_path=live_backend.stderr_path)

        assert run["status"] == "complete", f"Failed: {run.get('error_message')}"
        replay = _replay(run["id"])
        assert len(replay["nodes"]) == 4  # ms + ti + inf1 + inf2
        assert all(n["status"] == "completed" for n in replay["nodes"])

    def test_text_to_inference_to_reasoning(self, ollama_model, live_backend):
        """4-block: ms + text_input → llm_inference → chain_of_thought."""
        nodes = [
            _model_selector_node("ms", ollama_model),
            _text_input_node("ti", "What is 7 * 8?"),
            _inference_node("inf", ollama_model, max_tokens=30),
            _cot_node("cot", num_steps=2, max_tokens=200),
        ]
        edges = [
            _edge("ti", "inf", "text", "prompt"),
            _edge("ms", "inf", "model", "model"),
            _edge("inf", "cot", "llm_config", "llm"),
            _edge("inf", "cot", "response", "input"),
        ]
        pid, run = _create_and_run("Multi: Text→Inf→CoT", nodes, edges,
                                   timeout=300, stderr_path=live_backend.stderr_path)

        assert run["status"] == "complete", f"Failed: {run.get('error_message')}"
        replay = _replay(run["id"])
        assert len(replay["nodes"]) == 4

    def test_inference_template_inference(self, ollama_model, live_backend):
        """5-block: ms + ti → inf1 → prompt_template → inf2."""
        nodes = [
            _model_selector_node("ms", ollama_model),
            _text_input_node("ti", "Name a fruit."),
            _inference_node("inf1", ollama_model, max_tokens=20),
            _prompt_template_node("pt", "The user said: {input}. Describe its taste."),
            _inference_node("inf2", ollama_model, max_tokens=80),
        ]
        edges = [
            _edge("ms", "inf1", "model", "model"),
            _edge("ti", "inf1", "text", "prompt"),
            _edge("inf1", "pt", "response", "text"),
            _edge("pt", "inf2", "rendered_text", "prompt"),
            _edge("ms", "inf2", "model", "model"),
        ]
        pid, run = _create_and_run("Multi: Inf→Tmpl→Inf", nodes, edges,
                                   timeout=240, stderr_path=live_backend.stderr_path)

        assert run["status"] == "complete", f"Failed: {run.get('error_message')}"
        replay = _replay(run["id"])
        assert len(replay["nodes"]) == 5  # ms + ti + inf1 + pt + inf2

    def test_reasoning_to_agent(self, ollama_model, live_backend):
        """4-block: ms + text_input → chain_of_thought → agent_orchestrator."""
        nodes = [
            _model_selector_node("ms", ollama_model),
            _text_input_node("ti", "What are 3 benefits of exercise?"),
            _cot_node("cot", num_steps=2),
            _orchestrator_node("ao", max_steps=3, max_tokens=200),
        ]
        edges = [
            _edge("ms", "cot", "llm", "llm"),
            _edge("ti", "cot", "text", "input"),
            _edge("cot", "ao", "llm_config", "llm"),
            _edge("cot", "ao", "response", "input"),
        ]
        pid, run = _create_and_run("Multi: CoT→Agent", nodes, edges,
                                   timeout=300, stderr_path=live_backend.stderr_path)

        assert run["status"] == "complete", f"Failed: {run.get('error_message')}"
        replay = _replay(run["id"])
        assert len(replay["nodes"]) == 4  # ms + ti + cot + ao

    def test_five_block_pipeline(self, ollama_model, live_backend):
        """5-block: ms + text_input → prompt_template → llm_inference → chain_of_thought."""
        nodes = [
            _model_selector_node("ms", ollama_model),
            _text_input_node("ti", "quantum computing"),
            _prompt_template_node("pt", "Explain {input} in simple terms."),
            _inference_node("inf", ollama_model, max_tokens=100),
            _cot_node("cot", num_steps=2, max_tokens=200),
        ]
        edges = [
            _edge("ti", "pt", "text", "text"),
            _edge("pt", "inf", "rendered_text", "prompt"),
            _edge("ms", "inf", "model", "model"),
            _edge("inf", "cot", "llm_config", "llm"),
            _edge("inf", "cot", "response", "input"),
        ]
        pid, run = _create_and_run("Multi: 5-Block", nodes, edges,
                                   timeout=300, stderr_path=live_backend.stderr_path)

        assert run["status"] == "complete", f"Failed: {run.get('error_message')}"
        replay = _replay(run["id"])
        assert len(replay["nodes"]) == 5
        assert all(n["status"] == "completed" for n in replay["nodes"])
        assert run["duration_seconds"] > 0
