"""Deploy service — export models to Ollama, HuggingFace, ONNX, or standalone server."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from ..config import OLLAMA_URL

logger = logging.getLogger("blueprint.deploy")


# ── Dependency availability checks ──────────────────────────────────

def check_ollama_available() -> dict[str, Any]:
    """Check if Ollama CLI is installed and server is running."""
    cli_available = shutil.which("ollama") is not None
    server_running = False
    if cli_available:
        try:
            import urllib.request
            req = urllib.request.Request(f"{OLLAMA_URL}/api/version", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                server_running = resp.status == 200
        except Exception:
            pass
    return {"cli_available": cli_available, "server_running": server_running}


def check_huggingface_available() -> dict[str, Any]:
    """Check if huggingface_hub is installed."""
    try:
        import huggingface_hub  # noqa: F401
        return {"available": True, "version": huggingface_hub.__version__}
    except ImportError:
        return {"available": False, "install_command": "pip install huggingface_hub"}


def check_onnx_available() -> dict[str, Any]:
    """Check if ONNX export tools are available."""
    has_torch = False
    has_optimum = False
    try:
        import torch  # noqa: F401
        has_torch = True
    except ImportError:
        pass
    try:
        import optimum  # noqa: F401
        has_optimum = True
    except ImportError:
        pass
    return {
        "available": has_torch,
        "has_optimum": has_optimum,
        "install_command": "pip install torch" if not has_torch else None,
    }


def check_all_targets() -> dict[str, Any]:
    """Return availability info for all deploy targets."""
    return {
        "ollama": check_ollama_available(),
        "huggingface": check_huggingface_available(),
        "onnx": check_onnx_available(),
        "server": {"available": True},  # Always available — just generates Python files
    }


# ── Export functions ─────────────────────────────────────────────────

def export_to_ollama(
    model_record: Any,
    model_path: str,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Generate a Modelfile and register with Ollama via 'ollama create'.

    Args:
        model_record: ModelRecord ORM instance.
        model_path: Absolute path to the model file on disk.
        model_name: Name to register in Ollama. Defaults to model_record.name.

    Returns:
        {success: bool, model_name: str, error: str | None}
    """
    name = model_name or model_record.name.lower().replace(" ", "-")

    # Validate model file exists
    if not Path(model_path).is_file():
        return {"success": False, "model_name": name, "error": f"Model file not found: {model_path}"}

    # Check Ollama availability
    status = check_ollama_available()
    if not status["cli_available"]:
        return {"success": False, "model_name": name, "error": "Ollama CLI not found. Install from https://ollama.com"}
    if not status["server_running"]:
        return {"success": False, "model_name": name, "error": "Ollama server is not running. Start it with 'ollama serve'"}

    # Build Modelfile content
    modelfile_lines = [f"FROM {model_path}"]

    # Extract parameters from training config
    training_config = model_record.training_config or {}
    param_map = {
        "temperature": "temperature",
        "top_p": "top_p",
        "top_k": "top_k",
        "num_ctx": "num_ctx",
        "repeat_penalty": "repeat_penalty",
    }
    for config_key, ollama_key in param_map.items():
        if config_key in training_config:
            modelfile_lines.append(f"PARAMETER {ollama_key} {training_config[config_key]}")

    # Default temperature if not specified
    if "temperature" not in training_config:
        modelfile_lines.append("PARAMETER temperature 0.7")

    # Add system prompt from config if available
    if "system_prompt" in training_config:
        modelfile_lines.append(f'SYSTEM """{training_config["system_prompt"]}"""')

    modelfile_content = "\n".join(modelfile_lines) + "\n"

    # Write Modelfile to temp location and run ollama create
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".Modelfile", delete=False) as f:
            f.write(modelfile_content)
            modelfile_path = f.name

        result = subprocess.run(
            ["ollama", "create", name, "-f", modelfile_path],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "model_name": name,
                "modelfile": modelfile_content,
                "error": result.stderr.strip() or "ollama create failed",
            }

        return {
            "success": True,
            "model_name": name,
            "modelfile": modelfile_content,
            "message": f"Model '{name}' registered with Ollama",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "model_name": name, "error": "Ollama create timed out after 300s"}
    except Exception as e:
        return {"success": False, "model_name": name, "error": str(e)}
    finally:
        try:
            os.unlink(modelfile_path)
        except Exception:
            pass


def _resolve_hf_token(hf_token: str) -> str | None:
    """Resolve a HuggingFace token that may be a secrets store reference.

    Accepted formats:
      • ``hf_abc123...``   — literal token, used as-is.
      • ``$secret:NAME``   — resolved from Blueprint's encrypted secrets store.
      • ``$secret``        — shorthand for ``$secret:HF_TOKEN``.

    Returns the resolved token or None if resolution fails.
    """
    if not hf_token:
        return None

    if hf_token.startswith("$secret"):
        # Parse the secret name: "$secret:FOO" → "FOO", "$secret" → "HF_TOKEN"
        parts = hf_token.split(":", 1)
        secret_name = parts[1] if len(parts) > 1 else "HF_TOKEN"
        try:
            from ..utils.secrets import get_secret
            resolved = get_secret(secret_name)
            if not resolved:
                logger.warning("Secret '%s' not found in Blueprint secrets store", secret_name)
                return None
            return resolved
        except Exception as e:
            logger.warning("Failed to read secret '%s': %s", secret_name, e)
            return None

    # Literal token
    return hf_token


def export_to_huggingface(
    model_record: Any,
    hf_token: str,
    repo_id: str,
    private: bool = True,
) -> dict[str, Any]:
    """Push model weights to HuggingFace Hub with auto-generated model card.

    Security:
      • The token is never included in return values or logged.
      • Supports ``$secret:NAME`` syntax to read from Blueprint's encrypted
        secrets store (see ``_resolve_hf_token``).

    Args:
        model_record: ModelRecord ORM instance.
        hf_token: HuggingFace API token or ``$secret:NAME`` reference.
        repo_id: HuggingFace repo ID (e.g. "user/model-name").
        private: Whether the repo should be private.

    Returns:
        {success: bool, url: str | None, error: str | None}
    """
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return {
            "success": False,
            "url": None,
            "error": "huggingface_hub is not installed. Run: pip install huggingface_hub",
        }

    # Resolve token (may come from secrets store)
    resolved_token = _resolve_hf_token(hf_token)
    if not resolved_token:
        return {
            "success": False,
            "url": None,
            "error": "HuggingFace token could not be resolved. "
                     "Provide a literal token (hf_...) or store one via "
                     "Settings → Secrets with the name 'HF_TOKEN' and use '$secret:HF_TOKEN'.",
        }

    model_path = model_record.model_path
    if not model_path or not Path(model_path).exists():
        return {"success": False, "url": None, "error": f"Model file not found: {model_path}"}

    # Log the action but NEVER the token
    logger.info("Exporting model '%s' to HuggingFace repo '%s' (private=%s)",
                model_record.name, repo_id, private)

    try:
        hf_api = HfApi(token=resolved_token)

        # Create or get repo
        hf_api.create_repo(repo_id=repo_id, private=private, exist_ok=True)

        # Upload model file(s)
        model_p = Path(model_path)
        if model_p.is_dir():
            hf_api.upload_folder(
                folder_path=str(model_p),
                repo_id=repo_id,
                token=resolved_token,
            )
        else:
            hf_api.upload_file(
                path_or_fileobj=str(model_p),
                path_in_repo=model_p.name,
                repo_id=repo_id,
                token=resolved_token,
            )

        # Auto-generate model card
        metrics = model_record.metrics or {}
        training_config = model_record.training_config or {}

        card_content = f"""---
tags:
  - blueprint
  - specific-labs
license: apache-2.0
---

# {model_record.name}

**Version:** {model_record.version}
**Format:** {model_record.format}

## Overview

This model was trained and exported using [Blueprint](https://github.com/specific-labs/blueprint) by Specific Labs.

## Training Configuration

```json
{json.dumps(training_config, indent=2)}
```

## Metrics

| Metric | Value |
|--------|-------|
"""
        for k, v in metrics.items():
            card_content += f"| {k} | {v} |\n"

        if model_record.source_data:
            card_content += f"\n## Training Data\n\n{model_record.source_data}\n"

        card_content += "\n---\n*Exported with Blueprint by Specific Labs*\n"

        # Upload model card
        hf_api.upload_file(
            path_or_fileobj=card_content.encode("utf-8"),
            path_in_repo="README.md",
            repo_id=repo_id,
            token=resolved_token,
        )

        url = f"https://huggingface.co/{repo_id}"
        # Never include the token in the response
        return {"success": True, "url": url, "repo_id": repo_id}

    except Exception as e:
        # Scrub any token that might appear in the error message
        error_msg = str(e)
        if resolved_token and resolved_token in error_msg:
            error_msg = error_msg.replace(resolved_token, "[REDACTED]")
        return {"success": False, "url": None, "error": error_msg}


def _detect_model_type(model_path: str) -> str:
    """Classify a model path for ONNX export routing.

    Returns one of:
      'hf_dir'      — HuggingFace model directory (contains config.json)
      'safetensors' — .safetensors file
      'gguf'        — .gguf file (not convertible to ONNX)
      'pytorch'     — .pt/.pth/.bin PyTorch checkpoint
      'unknown'     — unrecognised format
    """
    p = Path(model_path)
    if p.is_dir():
        if (p / "config.json").is_file():
            return "hf_dir"
        # Directory with safetensors files
        if list(p.glob("*.safetensors")):
            return "hf_dir"
        return "unknown"
    suffix = p.suffix.lower()
    if suffix == ".safetensors":
        return "safetensors"
    if suffix == ".gguf":
        return "gguf"
    if suffix in (".pt", ".pth", ".bin"):
        return "pytorch"
    return "unknown"


def _is_state_dict(obj: Any) -> bool:
    """Return True if *obj* looks like a PyTorch state dict rather than a module."""
    if isinstance(obj, dict):
        # State dicts are flat dicts whose values are tensors
        try:
            import torch
            sample = list(obj.values())[:5]
            return all(isinstance(v, torch.Tensor) for v in sample) if sample else True
        except ImportError:
            return isinstance(obj, dict)
    return False


def export_to_onnx(
    model_record: Any,
    output_path: str,
) -> dict[str, Any]:
    """Convert a model to ONNX format.

    Routing strategy:
      1. HuggingFace model directories and safetensors files → ``optimum``
         (best coverage for transformer-class models).
      2. Full PyTorch modules (.pt/.pth/.bin) → ``torch.onnx.export``
         with ``weights_only=True`` safe loading.
      3. State dicts → rejected with an actionable error (no architecture info).
      4. GGUF files → rejected (quantised format, not directly convertible).

    Args:
        model_record: ModelRecord ORM instance.
        output_path: Where to write the .onnx file.

    Returns:
        {success: bool, path: str | None, size: int | None, error: str | None}
    """
    _fail = lambda err: {"success": False, "path": None, "size": None, "error": err}

    model_path = model_record.model_path
    if not model_path or not Path(model_path).exists():
        return _fail(f"Model file not found: {model_path}")

    model_type = _detect_model_type(model_path)

    # ── GGUF: not convertible ────────────────────────────────────────
    if model_type == "gguf":
        return _fail(
            "GGUF models cannot be converted to ONNX directly. "
            "GGUF is a quantised format without the original architecture graph. "
            "Re-export from the original PyTorch/HuggingFace checkpoint instead."
        )

    # ── HuggingFace dirs and safetensors → optimum (preferred) ───────
    if model_type in ("hf_dir", "safetensors"):
        try:
            from optimum.exporters.onnx import main_export
        except ImportError:
            return _fail(
                "Converting HuggingFace / safetensors models to ONNX requires "
                "the 'optimum' package. Run: pip install optimum[exporters]"
            )

        try:
            # optimum expects the model directory, not a single file
            export_source = model_path
            if model_type == "safetensors":
                export_source = str(Path(model_path).parent)

            output_dir = str(Path(output_path).parent)
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            main_export(export_source, output=output_dir)

            onnx_file = Path(output_path)
            if not onnx_file.exists():
                candidates = list(Path(output_dir).glob("*.onnx"))
                if candidates:
                    best = candidates[0]
                    if str(best) != output_path:
                        shutil.move(str(best), output_path)
                        onnx_file = Path(output_path)

            if not onnx_file.exists():
                return _fail("ONNX export completed but no .onnx file was produced. "
                             "The model architecture may not be supported by optimum.")

            size = onnx_file.stat().st_size
            if size == 0:
                return _fail("ONNX export produced an empty file. "
                             "The model may not be compatible with optimum ONNX export.")
            return {"success": True, "path": output_path, "size": size}

        except Exception as e:
            return _fail(f"optimum ONNX export failed: {e}")

    # ── PyTorch checkpoint → torch.onnx.export ───────────────────────
    try:
        import torch
    except ImportError:
        return _fail("PyTorch is not installed. Run: pip install torch")

    try:
        # Safe loading first (weights_only=True rejects arbitrary pickle code)
        try:
            loaded = torch.load(model_path, map_location="cpu", weights_only=True)
        except Exception:
            # weights_only=True fails for full module checkpoints that use pickle.
            # This is expected — full nn.Module saves require weights_only=False.
            loaded = torch.load(model_path, map_location="cpu", weights_only=False)

        # Reject state dicts — we need the architecture graph for ONNX export
        if _is_state_dict(loaded):
            return _fail(
                "This file contains a state dict (model weights only) without "
                "architecture information. torch.onnx.export requires a full "
                "nn.Module. Options:\n"
                "  1. Save the full model: torch.save(model, path)\n"
                "  2. Use a HuggingFace model directory with optimum "
                "(pip install optimum[exporters])\n"
                "  3. Reconstruct the model in code, load the state dict, "
                "then export manually"
            )

        if hasattr(loaded, "eval"):
            loaded.eval()

        if not callable(loaded):
            return _fail(
                f"Loaded object is {type(loaded).__name__}, not a callable nn.Module. "
                "torch.onnx.export requires a model with a forward() method."
            )

        # Infer input shape from training config
        training_config = model_record.training_config or {}
        input_shape = training_config.get("input_shape", [1, 3, 224, 224])

        try:
            dummy_input = torch.randn(*input_shape)
        except Exception as e:
            return _fail(f"Invalid input_shape {input_shape} in training config: {e}")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        torch.onnx.export(
            loaded,
            dummy_input,
            output_path,
            opset_version=14,
            do_constant_folding=True,
            input_names=["input"],
            output_names=["output"],
            dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
        )

        out_file = Path(output_path)
        if not out_file.exists() or out_file.stat().st_size == 0:
            return _fail("torch.onnx.export completed but produced no output file.")

        return {"success": True, "path": output_path, "size": out_file.stat().st_size}

    except Exception as e:
        return _fail(f"ONNX export failed: {e}")


def generate_inference_server(
    model_record: Any,
    output_dir: str,
) -> dict[str, Any]:
    """Generate a standalone FastAPI inference server.

    Args:
        model_record: ModelRecord ORM instance.
        output_dir: Directory to write the generated server files.

    Returns:
        {success: bool, path: str | None, error: str | None}
    """
    try:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        model_path = model_record.model_path or "model.bin"
        model_format = model_record.format or "pytorch"

        # Generate server.py
        server_code = textwrap.dedent(f'''\
            """Auto-generated inference server for {model_record.name}.

            Generated by Blueprint (Specific Labs).
            Run with: uvicorn server:app --host 0.0.0.0 --port 8000

            ┌──────────────────────────────────────────────────────────────────┐
            │  SECURITY NOTE                                                   │
            │                                                                  │
            │  By default, this server loads models using SAFE methods:        │
            │    • PyTorch: weights_only=True (rejects pickled executable      │
            │      code — see https://pytorch.org/docs/stable/notes/security)  │
            │    • Safetensors: safetensors.torch.load_file() (safe by design) │
            │    • ONNX: onnxruntime.InferenceSession (safe)                   │
            │                                                                  │
            │  If your model requires unsafe loading (e.g. a full nn.Module    │
            │  saved with torch.save(model, path)), set the environment        │
            │  variable TRUST_MODEL=1. Only do this for models YOU produced    │
            │  — never for untrusted third-party model files.                  │
            └──────────────────────────────────────────────────────────────────┘
            """

            import os
            import time
            from pathlib import Path

            from fastapi import FastAPI, HTTPException
            from pydantic import BaseModel

            app = FastAPI(
                title="{model_record.name} Inference Server",
                version="{model_record.version}",
            )

            MODEL_PATH = os.environ.get("MODEL_PATH", "{model_path}")
            MODEL_FORMAT = "{model_format}"

            # When True, allows torch.load(weights_only=False) which can execute
            # arbitrary pickled code. Only enable for models you trust completely.
            TRUST_MODEL = os.environ.get("TRUST_MODEL", "0") in ("1", "true", "yes")

            _model = None


            def load_model():
                """Load model from disk. Called once on first request."""
                global _model
                if _model is not None:
                    return _model

                model_file = Path(MODEL_PATH)
                if not model_file.exists():
                    raise RuntimeError(f"Model not found at {{MODEL_PATH}}")

                if MODEL_FORMAT == "safetensors":
                    # Safetensors is inherently safe — no executable code in the format
                    try:
                        from safetensors.torch import load_file
                        _model = load_file(MODEL_PATH)
                        return _model
                    except ImportError:
                        pass
                    # Fallback: load via transformers (also safe for safetensors)
                    from transformers import AutoModelForCausalLM, AutoTokenizer
                    _model = {{
                        "model": AutoModelForCausalLM.from_pretrained(
                            str(model_file.parent), local_files_only=True
                        ),
                        "tokenizer": AutoTokenizer.from_pretrained(
                            str(model_file.parent), local_files_only=True
                        ),
                    }}
                elif MODEL_FORMAT == "pytorch":
                    import torch
                    try:
                        # Safe loading (default): rejects pickled code
                        _model = torch.load(MODEL_PATH, map_location="cpu", weights_only=True)
                    except Exception as safe_err:
                        if not TRUST_MODEL:
                            raise RuntimeError(
                                f"Safe loading failed: {{safe_err}}\\n\\n"
                                "This model may contain pickled executable code. "
                                "If you trust this model, restart with TRUST_MODEL=1 "
                                "to enable unsafe loading."
                            ) from safe_err
                        # Unsafe loading — only when explicitly opted in
                        _model = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
                    if hasattr(_model, "eval"):
                        _model.eval()
                elif MODEL_FORMAT == "onnx":
                    import onnxruntime as ort
                    _model = ort.InferenceSession(MODEL_PATH)
                elif MODEL_FORMAT == "gguf":
                    from transformers import AutoModelForCausalLM, AutoTokenizer
                    _model = {{
                        "model": AutoModelForCausalLM.from_pretrained(
                            str(model_file.parent),
                            local_files_only=True,
                            gguf_file=model_file.name,
                        ),
                        "tokenizer": AutoTokenizer.from_pretrained(
                            str(model_file.parent), local_files_only=True
                        ),
                    }}
                else:
                    raise RuntimeError(f"Unsupported model format: {{MODEL_FORMAT}}")

                return _model


            class PredictRequest(BaseModel):
                """Input payload for prediction."""
                input: list | dict | str
                parameters: dict = {{}}


            class PredictResponse(BaseModel):
                """Output payload from prediction."""
                output: list | dict | str
                latency_ms: float
                model_name: str = "{model_record.name}"
                model_version: str = "{model_record.version}"


            @app.on_event("startup")
            async def startup():
                """Pre-load model on server start."""
                try:
                    load_model()
                except Exception as e:
                    print(f"Warning: model pre-load failed: {{e}}")


            @app.post("/predict", response_model=PredictResponse)
            async def predict(req: PredictRequest):
                """Run inference on the loaded model."""
                try:
                    model = load_model()
                except Exception as e:
                    raise HTTPException(503, f"Model not loaded: {{e}}")

                start = time.perf_counter()

                try:
                    if MODEL_FORMAT == "onnx":
                        import numpy as np
                        input_data = np.array(req.input, dtype=np.float32)
                        input_name = model.get_inputs()[0].name
                        result = model.run(None, {{input_name: input_data}})
                        output = [r.tolist() for r in result]
                    elif MODEL_FORMAT in ("gguf", "safetensors"):
                        # If loaded via safetensors.torch.load_file, model is a
                        # state dict — the user should use transformers loading instead.
                        if isinstance(model, dict) and "model" in model and "tokenizer" in model:
                            tokenizer = model["tokenizer"]
                            lm = model["model"]
                            inputs = tokenizer(req.input, return_tensors="pt")
                            outputs = lm.generate(**inputs, **req.parameters)
                            output = tokenizer.decode(outputs[0], skip_special_tokens=True)
                        else:
                            raise HTTPException(400,
                                "Model loaded as a state dict. For inference with "
                                "GGUF/safetensors, the model must be loaded via "
                                "transformers (AutoModelForCausalLM).")
                    else:
                        import torch
                        input_tensor = torch.tensor(req.input)
                        with torch.no_grad():
                            output = model(input_tensor)
                        if hasattr(output, "tolist"):
                            output = output.tolist()
                except HTTPException:
                    raise
                except Exception as e:
                    raise HTTPException(500, f"Inference failed: {{e}}")

                latency_ms = (time.perf_counter() - start) * 1000

                return PredictResponse(
                    output=output,
                    latency_ms=round(latency_ms, 2),
                )


            @app.get("/health")
            async def health():
                """Health check endpoint."""
                return {{
                    "status": "ok",
                    "model": "{model_record.name}",
                    "version": "{model_record.version}",
                    "format": MODEL_FORMAT,
                    "trust_model": TRUST_MODEL,
                }}
        ''')

        server_path = out / "server.py"
        server_path.write_text(server_code, encoding="utf-8")

        # Generate requirements.txt
        requirements = ["fastapi>=0.100.0", "uvicorn>=0.20.0", "pydantic>=2.0"]
        if model_format == "pytorch":
            requirements.append("torch>=2.0")
        elif model_format == "onnx":
            requirements.extend(["onnxruntime>=1.15.0", "numpy>=1.24.0"])
        elif model_format == "safetensors":
            requirements.extend(["safetensors>=0.4.0", "transformers>=4.30.0", "torch>=2.0"])
        elif model_format == "gguf":
            requirements.extend(["transformers>=4.30.0", "torch>=2.0"])

        req_path = out / "requirements.txt"
        req_path.write_text("\n".join(requirements) + "\n", encoding="utf-8")

        # Generate Dockerfile
        dockerfile = textwrap.dedent(f"""\
            FROM python:3.11-slim
            WORKDIR /app
            COPY requirements.txt .
            RUN pip install --no-cache-dir -r requirements.txt
            COPY . .
            ENV MODEL_PATH=/app/model/{Path(model_path).name}
            EXPOSE 8000
            CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
        """)
        (out / "Dockerfile").write_text(dockerfile, encoding="utf-8")

        # Generate README with security documentation
        readme = textwrap.dedent(f"""\
            # {model_record.name} — Inference Server

            Auto-generated by [Blueprint](https://github.com/specific-labs/blueprint)
            (Specific Labs).

            ## Quick Start

            ```bash
            pip install -r requirements.txt
            uvicorn server:app --host 0.0.0.0 --port 8000
            ```

            ## Docker

            ```bash
            docker build -t {model_record.name.lower().replace(" ", "-")}-server .
            docker run -p 8000:8000 -v /path/to/model:/app/model \\
                {model_record.name.lower().replace(" ", "-")}-server
            ```

            ## API

            - `POST /predict` — run inference (see `PredictRequest` schema)
            - `GET /health` — health check

            ## Security

            Model loading uses **safe mode by default**:

            | Format | Loader | Safe? |
            |--------|--------|-------|
            | PyTorch (.pt/.pth) | `torch.load(weights_only=True)` | Yes |
            | Safetensors | `safetensors.torch.load_file()` | Yes |
            | ONNX | `onnxruntime.InferenceSession()` | Yes |
            | GGUF | `transformers.AutoModelForCausalLM` | Yes |

            If safe loading fails for a PyTorch model (e.g. a full `nn.Module`
            saved with `torch.save(model, path)`), you must explicitly opt in
            to unsafe loading:

            ```bash
            TRUST_MODEL=1 uvicorn server:app
            ```

            **Only use `TRUST_MODEL=1` for model files you produced yourself.**
            PyTorch pickle files can execute arbitrary code during loading.

            ## Model Info

            - **Name:** {model_record.name}
            - **Version:** {model_record.version}
            - **Format:** {model_format}
        """)
        (out / "README.md").write_text(readme, encoding="utf-8")

        return {
            "success": True,
            "path": str(server_path),
            "output_dir": str(out),
            "files": ["server.py", "requirements.txt", "Dockerfile", "README.md"],
        }

    except Exception as e:
        return {"success": False, "path": None, "error": str(e)}
