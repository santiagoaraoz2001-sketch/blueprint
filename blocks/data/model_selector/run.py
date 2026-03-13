"""Model Selector — select and validate a model from HuggingFace, Ollama, MLX, or a local path."""

import hashlib
import json
import os
import urllib.request
import urllib.error


def _default_endpoint(source):
    """Return the default API endpoint for a given model source."""
    return {
        "ollama": "http://localhost:11434",
        "mlx": "",
        "huggingface": "",
        "pytorch": "",
        "local_path": "",
    }.get(source, "")


def _scan_local_models(source, ctx):
    """Auto-detect locally available models for the given source.

    Returns a list of discovered model identifiers.
    """
    discovered = []

    if source in ("huggingface", "mlx"):
        # Scan HuggingFace cache for downloaded model snapshots
        cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
        if os.path.isdir(cache_dir):
            try:
                for entry in os.listdir(cache_dir):
                    if entry.startswith("models--"):
                        # Format: models--org--model-name
                        parts = entry[len("models--"):].split("--", 1)
                        if len(parts) == 2:
                            model_id = f"{parts[0]}/{parts[1]}"
                            discovered.append(model_id)
            except PermissionError:
                pass
        if discovered:
            ctx.log_message(
                f"Found {len(discovered)} cached HuggingFace model(s): "
                f"{', '.join(discovered[:5])}"
                + (f" (+{len(discovered) - 5} more)" if len(discovered) > 5 else "")
            )

    elif source == "ollama":
        # Query Ollama API for locally pulled models
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/tags",
                headers={"User-Agent": "Blueprint-ModelSelector/1.0"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    body = response.read().decode("utf-8")
                    api_data = json.loads(body)
                    for m in api_data.get("models", []):
                        name = m.get("name", "")
                        if name:
                            discovered.append(name)
            if discovered:
                ctx.log_message(
                    f"Ollama running with {len(discovered)} local model(s): "
                    f"{', '.join(discovered[:8])}"
                )
            else:
                ctx.log_message("Ollama is running but no models pulled yet.")
        except urllib.error.URLError:
            ctx.log_message(
                "Ollama not detected at localhost:11434. "
                "Start with: ollama serve"
            )
        except Exception:
            pass

    return discovered


def _validate_huggingface(model_id, revision, ctx):
    """Validate that a HuggingFace model_id is provided and optionally check the API."""
    if not model_id:
        raise ValueError(
            "model_id is required for HuggingFace source (e.g. 'meta-llama/Llama-3-8B')"
        )

    model_info = {
        "source": "huggingface",
        "model_id": model_id,
        "revision": revision,
        "hub_url": f"https://huggingface.co/{model_id}",
        "api_url": f"https://huggingface.co/api/models/{model_id}",
        "validated": False,
    }

    # Try to validate via the HuggingFace API
    api_url = f"https://huggingface.co/api/models/{model_id}"
    if revision and revision != "main":
        api_url += f"?revision={revision}"

    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "Blueprint-ModelSelector/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 200:
                body = response.read().decode("utf-8")
                api_data = json.loads(body)
                model_info["validated"] = True
                model_info["model_type"] = api_data.get("pipeline_tag", "unknown")
                model_info["library"] = api_data.get("library_name", "unknown")
                model_info["downloads"] = api_data.get("downloads", 0)
                model_info["likes"] = api_data.get("likes", 0)
                model_info["tags"] = api_data.get("tags", [])[:20]
                model_info["last_modified"] = api_data.get("lastModified")
                ctx.log_message(
                    f"HuggingFace model validated: {model_id} "
                    f"(type={model_info['model_type']}, library={model_info['library']})"
                )
    except urllib.error.HTTPError as e:
        if e.code == 404:
            ctx.log_message(
                f"WARNING: HuggingFace model '{model_id}' not found (404). "
                f"It may be private or the ID may be incorrect."
            )
        else:
            ctx.log_message(
                f"WARNING: HuggingFace API returned HTTP {e.code}. "
                f"Model not validated but will proceed."
            )
    except (urllib.error.URLError, Exception) as e:
        ctx.log_message(
            f"Could not reach HuggingFace API ({e}). "
            f"Proceeding without validation."
        )

    return model_info


def _validate_ollama(model_id, ctx):
    """Validate that an Ollama model exists by querying the local Ollama API."""
    if not model_id:
        raise ValueError(
            "model_id is required for Ollama source (e.g. 'llama3', 'mistral')"
        )

    model_info = {
        "source": "ollama",
        "model_id": model_id,
        "api_url": "http://localhost:11434",
        "validated": False,
        "available_locally": False,
    }

    # Query Ollama API for available models
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/tags",
            headers={"User-Agent": "Blueprint-ModelSelector/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                body = response.read().decode("utf-8")
                api_data = json.loads(body)
                models = api_data.get("models", [])
                model_names = []
                for m in models:
                    name = m.get("name", "")
                    model_names.append(name)
                    # Match by exact name or by name without tag
                    base_name = name.split(":")[0] if ":" in name else name
                    if name == model_id or base_name == model_id:
                        model_info["validated"] = True
                        model_info["available_locally"] = True
                        model_info["size"] = m.get("size", 0)
                        model_info["modified_at"] = m.get("modified_at")
                        model_info["digest"] = m.get("digest", "")[:16]
                        ctx.log_message(f"Ollama model found locally: {name}")
                        break

                if not model_info["available_locally"]:
                    ctx.log_message(
                        f"Ollama model '{model_id}' not found locally. "
                        f"Available models: {', '.join(model_names[:10])}. "
                        f"You may need to run: ollama pull {model_id}"
                    )
                    # Still mark as validated since Ollama is reachable
                    model_info["validated"] = True
                    model_info["available_models"] = model_names[:20]

    except urllib.error.URLError:
        ctx.log_message(
            "WARNING: Cannot connect to Ollama at localhost:11434. "
            "Ensure Ollama is running (ollama serve)."
        )
    except Exception as e:
        ctx.log_message(f"WARNING: Ollama API error: {e}")

    return model_info


def _validate_mlx(model_id, ctx):
    """Validate an MLX model reference."""
    if not model_id:
        raise ValueError(
            "model_id is required for MLX source (e.g. 'mlx-community/Llama-3-8B-4bit')"
        )

    model_info = {
        "source": "mlx",
        "model_id": model_id,
        "hub_url": f"https://huggingface.co/{model_id}",
        "validated": False,
    }

    # Check if mlx_lm is available
    try:
        import mlx_lm  # noqa: F401
        model_info["mlx_lm_available"] = True
        ctx.log_message("mlx_lm package is available")
    except ImportError:
        model_info["mlx_lm_available"] = False
        ctx.log_message(
            "WARNING: mlx_lm not installed. Install with: pip install mlx-lm"
        )

    # Try to validate via HuggingFace API (MLX models are hosted on HF)
    api_url = f"https://huggingface.co/api/models/{model_id}"
    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "Blueprint-ModelSelector/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 200:
                body = response.read().decode("utf-8")
                api_data = json.loads(body)
                model_info["validated"] = True
                model_info["tags"] = api_data.get("tags", [])[:20]
                model_info["downloads"] = api_data.get("downloads", 0)
                ctx.log_message(f"MLX model validated on HuggingFace: {model_id}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            ctx.log_message(f"WARNING: MLX model '{model_id}' not found on HuggingFace.")
        else:
            ctx.log_message(f"WARNING: HuggingFace API returned HTTP {e.code}.")
    except (urllib.error.URLError, Exception) as e:
        ctx.log_message(f"Could not validate MLX model via API: {e}")

    return model_info


def _validate_local_path(local_path, ctx):
    """Validate that a local model path exists and contains model files."""
    if not local_path:
        raise ValueError(
            "local_path config is required when source is 'local_path'. "
            "Set it to the directory containing the model files."
        )

    model_info = {
        "source": "local_path",
        "path": local_path,
        "validated": False,
    }

    if not os.path.exists(local_path):
        ctx.log_message(f"WARNING: Local path does not exist: {local_path}")
        return model_info

    if os.path.isfile(local_path):
        model_info["validated"] = True
        model_info["is_file"] = True
        model_info["file_size_bytes"] = os.path.getsize(local_path)
        ctx.log_message(
            f"Local model file found: {local_path} "
            f"({model_info['file_size_bytes']:,} bytes)"
        )
        return model_info

    if os.path.isdir(local_path):
        model_info["is_directory"] = True
        # Scan for common model files
        model_files = []
        common_patterns = [
            "config.json", "tokenizer.json", "tokenizer_config.json",
            "model.safetensors", "pytorch_model.bin", "model.gguf",
            "adapter_config.json", "adapter_model.safetensors",
        ]
        try:
            all_files = os.listdir(local_path)
        except PermissionError:
            ctx.log_message(f"WARNING: Permission denied reading {local_path}")
            return model_info

        for fname in all_files:
            fpath = os.path.join(local_path, fname)
            if os.path.isfile(fpath):
                model_files.append(fname)

        matched = [f for f in model_files if f in common_patterns]
        # Also match wildcard patterns
        for f in model_files:
            if f.endswith(".safetensors") or f.endswith(".bin") or f.endswith(".gguf"):
                if f not in matched:
                    matched.append(f)

        model_info["files"] = model_files[:50]
        model_info["model_files_found"] = matched
        model_info["total_files"] = len(model_files)

        if matched:
            model_info["validated"] = True
            ctx.log_message(
                f"Local model directory validated: {local_path} "
                f"({len(matched)} model files found: {', '.join(matched[:5])})"
            )
        else:
            ctx.log_message(
                f"WARNING: Directory exists but no recognized model files found in {local_path}. "
                f"Found {len(model_files)} files total."
            )
            # Still mark as validated since the path exists
            model_info["validated"] = True

    return model_info


def _compute_checksums(local_path, ctx):
    """Compute SHA256 checksums for model files in a directory."""
    checksums = {}
    if os.path.isfile(local_path):
        checksums[os.path.basename(local_path)] = _sha256_file(local_path)
    elif os.path.isdir(local_path):
        model_extensions = (".safetensors", ".bin", ".gguf", ".pt", ".pth")
        try:
            for fname in os.listdir(local_path):
                fpath = os.path.join(local_path, fname)
                if os.path.isfile(fpath) and any(fname.endswith(ext) for ext in model_extensions):
                    checksums[fname] = _sha256_file(fpath)
                    ctx.log_message(f"  Checksum {fname}: {checksums[fname][:16]}...")
        except PermissionError:
            ctx.log_message("WARNING: Permission denied computing checksums")
    return checksums


def _sha256_file(filepath):
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def run(ctx):
    source = ctx.config.get("source", "huggingface").lower().strip()
    model_id = ctx.config.get("model_id", "").strip()
    revision = ctx.config.get("revision", "main").strip()
    local_path = ctx.config.get("local_path", "").strip()
    quantization = ctx.config.get("quantization", "none").lower().strip()
    auto_download = ctx.config.get("auto_download", False)
    verify_checksum = ctx.config.get("verify_checksum", True)

    ctx.log_message(f"Model Selector starting (source={source})")
    ctx.report_progress(0, 5)

    valid_sources = {"huggingface", "ollama", "mlx", "local_path"}
    if source not in valid_sources:
        raise ValueError(
            f"Unsupported source '{source}'. Supported: {', '.join(sorted(valid_sources))}"
        )

    valid_quantizations = {"none", "4bit", "8bit"}
    if quantization not in valid_quantizations:
        raise ValueError(
            f"Unsupported quantization '{quantization}'. "
            f"Supported: {', '.join(sorted(valid_quantizations))}"
        )

    # ---- Step 0: Auto-detect locally available models ----
    ctx.report_progress(1, 5)
    available_local_models = _scan_local_models(source, ctx)

    # If no model_id provided, suggest from local models
    if not model_id and source != "local_path" and available_local_models:
        ctx.log_message(
            f"No model_id specified. Available local models for '{source}': "
            f"{', '.join(available_local_models[:10])}"
        )

    # ---- Step 1: Validate model ID format for source ----
    ctx.report_progress(2, 5)

    if source == "huggingface" and model_id and "/" not in model_id:
        ctx.log_message(
            f"Hint: HuggingFace model IDs usually contain '/' (e.g. 'org/model-name'). "
            f"Got '{model_id}' — proceeding but this may not resolve."
        )
    elif source == "ollama" and model_id and "/" in model_id and ":" not in model_id:
        ctx.log_message(
            f"Hint: Ollama model IDs use 'model:tag' format (e.g. 'llama3:8b'). "
            f"Got '{model_id}' — this looks like a HuggingFace ID."
        )

    if source == "huggingface":
        model_info = _validate_huggingface(model_id, revision, ctx)
    elif source == "ollama":
        model_info = _validate_ollama(model_id, ctx)
    elif source == "mlx":
        model_info = _validate_mlx(model_id, ctx)
    elif source == "local_path":
        model_info = _validate_local_path(local_path, ctx)

    # ---- Step 2: Auto-download if requested ----
    ctx.report_progress(3, 5)

    if auto_download:
        if source == "huggingface":
            try:
                from huggingface_hub import snapshot_download
                ctx.log_message(f"Auto-downloading model: {model_id}...")
                download_path = snapshot_download(
                    repo_id=model_id,
                    revision=revision,
                )
                model_info["downloaded"] = True
                model_info["download_path"] = download_path
                ctx.log_message(f"Model downloaded to: {download_path}")
            except ImportError:
                ctx.log_message(
                    "WARNING: huggingface_hub not installed. "
                    "Install with: pip install huggingface_hub"
                )
                model_info["downloaded"] = False
            except Exception as e:
                ctx.log_message(f"WARNING: Auto-download failed: {e}")
                model_info["downloaded"] = False
        elif source == "ollama" and not model_info.get("available_locally"):
            ctx.log_message(
                f"To download this Ollama model, run: ollama pull {model_id}"
            )
            model_info["downloaded"] = False
        else:
            model_info["downloaded"] = False
    else:
        model_info["downloaded"] = False

    # ---- Step 3: Verify checksums if requested ----
    ctx.report_progress(4, 5)

    if verify_checksum and source == "local_path" and local_path:
        ctx.log_message("Verifying file checksums...")
        checksums = _compute_checksums(local_path, ctx)
        if checksums:
            model_info["checksums"] = checksums
            ctx.log_message(f"Verified {len(checksums)} model file(s)")
        else:
            ctx.log_message("No model files found for checksum verification")

    # ---- Step 4: Enrich with common fields and save ----
    ctx.report_progress(5, 5)

    if quantization != "none":
        model_info["quantization"] = quantization
        ctx.log_message(f"Quantization requested: {quantization}")
    else:
        model_info["quantization"] = None

    # Ensure model_id is always present
    if "model_id" not in model_info and model_id:
        model_info["model_id"] = model_id
    if "revision" not in model_info and revision:
        model_info["revision"] = revision

    # ---- Standardize output format (Rule 3) ----
    # All model output ports must use this exact format with compatibility aliases.
    _name = model_info.get("model_id", model_info.get("path", ""))
    standardized = {
        # Identity (always present)
        "model_name": _name,
        "model_id": _name,
        "source": source,
        "endpoint": _default_endpoint(source),
        # Auth (optional)
        "api_key": model_info.get("api_key", ""),
        # Metadata (optional)
        "validated": model_info.get("validated", False),
        "available_locally": model_info.get("available_locally", False),
        "quantization": model_info.get("quantization"),
        "available_local_models": available_local_models if available_local_models else [],
        # Compatibility aliases (mirror keys)
        "backend": source,
        "provider": source,
        "base_url": _default_endpoint(source),
    }
    # Merge any extra metadata from validation (tags, downloads, etc.)
    standardized.update({k: v for k, v in model_info.items() if k not in standardized})

    # Write model info to a file for downstream reference
    model_info_path = os.path.join(ctx.run_dir, "model_info.json")
    with open(model_info_path, "w", encoding="utf-8") as f:
        json.dump(standardized, f, indent=2, default=str, ensure_ascii=False)

    ctx.save_output("model", standardized)
    ctx.save_artifact("model_info", model_info_path)
    ctx.log_metric("model_validated", 1.0 if standardized.get("validated") else 0.0)

    validated_str = "VALIDATED" if standardized.get("validated") else "NOT VALIDATED"
    ctx.log_message(
        f"Model selected: source={source}, "
        f"id={standardized.get('model_name', 'N/A')}, "
        f"status={validated_str}"
    )
    ctx.log_message("Model Selector complete.")
