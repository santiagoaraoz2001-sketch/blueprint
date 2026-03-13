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


def run(ctx):
    dataset_path = ctx.load_input("dataset")
    text_column = ctx.config.get("text_column", "text")
    model_name = ctx.config.get("model_name", "all-MiniLM-L6-v2")
    provider = ctx.config.get("backend", ctx.config.get("provider", "sentence-transformers"))
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")
    api_key = ctx.config.get("api_key", "") or os.environ.get("OPENAI_API_KEY", "")
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
    with open(data_file, "r", encoding="utf-8") as f:
        rows = json.load(f)

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

            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch_embs = st_model.encode(batch, show_progress_bar=False)
                embeddings.extend(batch_embs.tolist())
                ctx.report_progress(min(i + batch_size, len(texts)), len(texts))

        except ImportError:
            ctx.log_message("sentence-transformers not installed. Install: pip install sentence-transformers")
            ctx.log_message("Falling back to demo embeddings.")
            method_used = "demo"
            embeddings = _demo_embeddings(texts, 384)
            embedding_dim = 384

    # ── Ollama ───────────────────────────────────────────────────
    elif provider == "ollama":
        ep = endpoint.rstrip("/")
        ctx.log_message(f"Using Ollama embeddings at {ep}")

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
            except Exception:
                # Fall back to single-item endpoint
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
            raise ValueError("OpenAI API key required. Set api_key config or OPENAI_API_KEY env var.")

        ep = endpoint.rstrip("/") if endpoint and "openai" in endpoint else "https://api.openai.com"
        openai_model = model_name if model_name != "all-MiniLM-L6-v2" else "text-embedding-3-small"
        ctx.log_message(f"Using OpenAI embeddings: {openai_model}")

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
        ctx.log_message(f"Unknown provider '{provider}'. Using demo embeddings.")
        method_used = "demo"
        embeddings = _demo_embeddings(texts, 384)
        embedding_dim = 384

    if not embedding_dim:
        embedding_dim = 384

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

    # Save embeddings alongside original data
    results = []
    for i, row in enumerate(rows):
        entry = dict(row) if isinstance(row, dict) else {"text": str(row)}
        entry[embedding_column] = embeddings[i] if i < len(embeddings) else [0.0] * embedding_dim
        results.append(entry)

    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(results, f)

    if output_format == "json":
        emb_path = os.path.join(ctx.run_dir, "embeddings.json")
        emb_data = {
            "embeddings": embeddings,
            "labels": [str(row.get("label", row.get("text", row.get("id", i)))) if isinstance(row, dict) else str(row) for i, row in enumerate(rows)],
            "model": model_name,
            "dimensions": embedding_dim,
        }
        with open(emb_path, "w", encoding="utf-8") as f:
            json.dump(emb_data, f)
    else:
        try:
            import numpy as np
            emb_path = os.path.join(ctx.run_dir, "embeddings.npy")
            np.save(emb_path, np.array(embeddings, dtype=np.float32))
        except ImportError:
            emb_path = os.path.join(ctx.run_dir, "embeddings.json")
            emb_data = {
                "embeddings": embeddings,
                "labels": [str(row.get("label", row.get("text", row.get("id", i)))) if isinstance(row, dict) else str(row) for i, row in enumerate(rows)],
                "model": model_name,
                "dimensions": embedding_dim,
            }
            with open(emb_path, "w", encoding="utf-8") as f:
                json.dump(emb_data, f)

    ctx.save_output("dataset", out_dir)
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
