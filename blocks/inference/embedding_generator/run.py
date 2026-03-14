"""Embedding Generator — generate vector embeddings for text data.

Workflows:
  1. Semantic search: documents -> embeddings -> similarity search
  2. Clustering: text dataset -> embeddings -> cluster analysis
  3. RAG pipeline: knowledge base -> embeddings -> vector store
  4. Deduplication: text corpus -> embeddings -> find near-duplicates
  5. Classification: text -> embeddings -> downstream classifier
"""

import json
import math
import os
import urllib.request

try:
    from backend.block_sdk.exceptions import (
        BlockConfigError, BlockInputError, BlockDataError,
        BlockDependencyError, BlockExecutionError,
    )
except ImportError:
    class BlockConfigError(ValueError):
        def __init__(self, field, message, **kw): super().__init__(message)
    class BlockInputError(ValueError):
        def __init__(self, message, **kw): super().__init__(message)
    class BlockDataError(ValueError):
        pass
    class BlockDependencyError(ImportError):
        def __init__(self, dep, message="", **kw): super().__init__(message or dep)
    class BlockExecutionError(RuntimeError):
        def __init__(self, message, **kw): super().__init__(message)

_DEFAULT_DEMO_DIM = 384
_DEFAULT_ENDPOINT = "http://localhost:11434"


def _row_label(row, index):
    """Extract a display label from a row."""
    if isinstance(row, dict):
        return str(row.get("label", row.get("text", row.get("id", index))))
    return str(row)


def run(ctx):
    dataset_path = ctx.resolve_as_file_path("dataset")

    # Read upstream dataset metadata
    _dataset_meta = {}
    try:
        _meta_input = ctx.load_input("dataset_meta")
        if isinstance(_meta_input, dict):
            _dataset_meta = _meta_input
    except (ValueError, KeyError):
        pass

    text_column = _dataset_meta.get("text_column", ctx.config.get("text_column", "text"))

    # ── Model config: upstream model input takes priority ──────────────
    model_data = {}
    if ctx.inputs.get("model"):
        try:
            raw_model = ctx.load_input("model")
            if isinstance(raw_model, str) and os.path.isfile(raw_model):
                with open(raw_model, "r", encoding="utf-8") as f:
                    raw_model = json.load(f)
            if isinstance(raw_model, dict):
                model_data = raw_model
                ctx.log_message(f"Using connected model: {model_data.get('model_name', 'unknown')}")
        except Exception as e:
            ctx.log_message(f"Warning: could not load model input: {e}")

    provider = model_data.get("source", model_data.get("backend",
        ctx.config.get("backend", ctx.config.get("provider", "sentence-transformers"))))
    model_name = model_data.get("model_name", model_data.get("model_id",
        ctx.config.get("model_name", "all-MiniLM-L6-v2")))
    endpoint = model_data.get("endpoint", model_data.get("base_url",
        ctx.config.get("endpoint", _DEFAULT_ENDPOINT)))
    api_key = model_data.get("api_key",
        ctx.config.get("api_key", "")) or os.environ.get("OPENAI_API_KEY", "")

    # Config conflict warnings
    if ctx.inputs.get("model") and model_data and ctx.config.get("model_name"):
        ctx.log_message(
            f"\u26a0 Config conflict: upstream model='{model_data.get('model_name')}' "
            f"but local config has model_name='{ctx.config.get('model_name')}'. "
            f"Using upstream. Clear local config to remove this warning."
        )
    batch_size = int(ctx.config.get("batch_size", 32))
    embedding_column = ctx.config.get("embedding_column", "_embedding")
    output_format = ctx.config.get("output_format", "numpy")
    normalize = ctx.config.get("normalize", False)
    if isinstance(normalize, str):
        normalize = normalize.lower() in ("true", "1", "yes")
    truncate_length = int(ctx.config.get("truncate_length", 0))
    dimensions = int(ctx.config.get("dimensions", 0))

    # Load dataset
    data_file = os.path.join(dataset_path, "data.json") if os.path.isdir(dataset_path) else dataset_path
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            rows = json.load(f)
    except FileNotFoundError:
        raise BlockInputError(f"Dataset file not found: {data_file}", details="Check that the upstream block produced output", recoverable=False)
    except json.JSONDecodeError as e:
        raise BlockDataError(f"Invalid JSON in dataset file {data_file}: {e}")

    # Normalize to list of rows
    if isinstance(rows, dict):
        rows = rows.get("data", rows.get("rows", rows.get("documents", [rows])))
    if not isinstance(rows, list):
        raise BlockDataError(
            f"Expected a JSON array in {data_file}, got {type(rows).__name__}. "
            f"The dataset should be a JSON array of objects."
        )

    # Extract texts
    texts = []
    for row in rows:
        if isinstance(row, dict):
            texts.append(str(row.get(text_column, row.get("content", ""))))
        else:
            texts.append(str(row))

    # Truncate texts if configured
    if truncate_length > 0:
        texts = [t[:truncate_length] for t in texts]

    ctx.log_message(f"Generating embeddings for {len(texts)} texts")
    ctx.log_message(f"Model: {model_name}, Provider: {provider}")
    if texts:
        ctx.report_progress(0, len(texts))

    embeddings = []
    embedding_dim = 0
    method_used = provider

    # ── Sentence Transformers ────────────────────────────────────
    if provider == "sentence-transformers":
        try:
            from sentence_transformers import SentenceTransformer

            ctx.log_message("Loading sentence-transformers model...")
            st_model = SentenceTransformer(model_name)
            embedding_dim = st_model.get_sentence_embedding_dimension()
            ctx.log_message(f"Loaded. Dimension: {embedding_dim}")
            ctx.log_metric("simulation_mode", 0.0)

            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch_embs = st_model.encode(batch, show_progress_bar=False)
                embeddings.extend(batch_embs.tolist())
                ctx.report_progress(min(i + batch_size, len(texts)), len(texts))

        except ImportError as e:
            from backend.block_sdk.exceptions import BlockDependencyError
            missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
            raise BlockDependencyError(
                missing,
                f"Required library not installed: {e}",
                install_hint="pip install sentence-transformers",
            )

    # ── Ollama ───────────────────────────────────────────────────
    elif provider == "ollama":
        ep = endpoint.rstrip("/")
        ctx.log_message(f"Using Ollama embeddings at {ep}")
        ctx.log_metric("simulation_mode", 0.0)

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            # Try batch endpoint first (Ollama >= 0.5)
            try:
                url = f"{ep}/api/embed"
                payload = json.dumps({"model": model_name, "input": batch}).encode()
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode())
                    batch_embs = data.get("embeddings", [])
                    embeddings.extend(batch_embs)
                    if not embedding_dim and batch_embs:
                        embedding_dim = len(batch_embs[0])
            except Exception as batch_err:
                # Fall back to single-item endpoint (older Ollama versions)
                ctx.log_message(f"Batch endpoint failed ({batch_err}), falling back to single-item mode")
                for text in batch:
                    try:
                        url = f"{ep}/api/embeddings"
                        payload = json.dumps({"model": model_name, "prompt": text}).encode()
                        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                        with urllib.request.urlopen(req, timeout=60) as resp:
                            data = json.loads(resp.read().decode())
                            emb = data.get("embedding", [])
                            embeddings.append(emb)
                            if not embedding_dim and emb:
                                embedding_dim = len(emb)
                    except Exception as e:
                        ctx.log_message(f"Ollama error: {e}")
                        embeddings.append([])

            ctx.report_progress(min(i + batch_size, len(texts)), len(texts))

        if embedding_dim:
            ctx.log_message(f"Dimension: {embedding_dim}")

    # ── OpenAI ───────────────────────────────────────────────────
    elif provider == "openai":
        if not api_key:
            raise BlockConfigError("api_key", "OpenAI API key required. Set api_key config or OPENAI_API_KEY env var.")

        # Use custom endpoint if explicitly configured, otherwise default to OpenAI API
        if endpoint and endpoint.rstrip("/") != _DEFAULT_ENDPOINT:
            ep = endpoint.rstrip("/")
        else:
            ep = "https://api.openai.com"
        openai_model = model_name if model_name != "all-MiniLM-L6-v2" else "text-embedding-3-small"
        ctx.log_message(f"Using OpenAI embeddings: {openai_model}")
        ctx.log_metric("simulation_mode", 0.0)

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            url = f"{ep}/v1/embeddings"
            payload_dict = {"model": openai_model, "input": batch}
            if dimensions > 0:
                payload_dict["dimensions"] = dimensions
            payload = json.dumps(payload_dict).encode()
            req = urllib.request.Request(url, data=payload, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            })
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode())
                    for item in data.get("data", []):
                        emb = item.get("embedding", [])
                        embeddings.append(emb)
                        if not embedding_dim and emb:
                            embedding_dim = len(emb)
            except Exception as e:
                ctx.log_message(f"OpenAI error at batch {i}: {e}")
                embeddings.extend([[] for _ in batch])

            ctx.report_progress(min(i + batch_size, len(texts)), len(texts))

        if embedding_dim:
            ctx.log_message(f"Dimension: {embedding_dim}")

    # ── Unknown provider ─────────────────────────────────────────
    else:
        ctx.log_message(f"⚠️ SIMULATION MODE: Unknown provider '{provider}'. Using synthetic demo embeddings. Supported providers: sentence-transformers, ollama, openai.")
        ctx.log_metric("simulation_mode", 1.0)
        method_used = "demo"
        embeddings = _demo_embeddings(texts, _DEFAULT_DEMO_DIM)
        embedding_dim = _DEFAULT_DEMO_DIM

    if not embedding_dim:
        embedding_dim = _DEFAULT_DEMO_DIM

    # Pad any missing embeddings
    for i in range(len(embeddings)):
        if not embeddings[i]:
            embeddings[i] = [0.0] * embedding_dim

    # Normalize embeddings if configured
    if normalize:
        for i in range(len(embeddings)):
            if embeddings[i]:
                norm = math.sqrt(sum(v * v for v in embeddings[i])) or 1.0
                embeddings[i] = [round(v / norm, 6) for v in embeddings[i]]

    # ── Compute labels once for reuse ─────────────────────────────
    labels = [_row_label(row, i) for i, row in enumerate(rows)]

    # ── Save dataset with embedded vectors ────────────────────────
    results = []
    for i, row in enumerate(rows):
        entry = dict(row) if isinstance(row, dict) else {"text": str(row)}
        entry[embedding_column] = embeddings[i] if i < len(embeddings) else [0.0] * embedding_dim
        results.append(entry)

    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(results, f)


    ctx.save_output("dataset", out_dir)

    # ── Save format-specific artifact (for manual download/inspection) ──
    if output_format == "numpy":
        try:
            import numpy as np
            npy_path = os.path.join(ctx.run_dir, "embeddings.npy")
            np.save(npy_path, np.array(embeddings, dtype=np.float32))
        except ImportError as e:
            from backend.block_sdk.exceptions import BlockDependencyError
            missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
            raise BlockDependencyError(
                missing,
                f"Required library not installed: {e}",
                install_hint="pip install numpy",
            )

    # ── Save structured embeddings output for pipeline consumers ──
    # Always JSON for downstream block compatibility
    emb_output = {
        "embeddings": embeddings,
        "labels": labels,
        "model": model_name,
        "dimensions": embedding_dim,
    }
    emb_output_path = os.path.join(ctx.run_dir, "embeddings_output.json")
    with open(emb_output_path, "w", encoding="utf-8") as f:
        json.dump(emb_output, f)
    ctx.save_output("embeddings", emb_output_path)

    ctx.save_output("metrics", {
        "num_embeddings": len(embeddings),
        "embedding_dim": embedding_dim,
        "model": model_name,
        "provider": method_used,
        "embedding_column": embedding_column,
    })
    ctx.log_metric("num_embeddings", len(embeddings))
    ctx.log_metric("embedding_dim", embedding_dim)
    ctx.log_message(f"Done: {len(embeddings)} embeddings (dim={embedding_dim}) in column '{embedding_column}'")
    if texts:
        ctx.report_progress(len(texts), len(texts))


def _demo_embeddings(texts, dim):
    """Generate deterministic pseudo-embeddings for demo mode."""
    import hashlib

    embeddings = []
    for text in texts:
        h = hashlib.sha256(text.encode()).hexdigest()
        seed_val = int(h[:8], 16)
        emb = [round(math.sin(seed_val * (j + 1) * 0.001) * 0.5, 6) for j in range(dim)]
        norm = math.sqrt(sum(v * v for v in emb)) or 1.0
        emb = [round(v / norm, 6) for v in emb]
        embeddings.append(emb)
    return embeddings
