"""Vector Store Builder — index text chunks into a local ChromaDB or FAISS vector store."""

import json
import os
import time

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


def _load_json(path):
    """Load data from a file path (JSON or numpy .npy)."""
    if not path or not os.path.isfile(path):
        return None
    ext = os.path.splitext(path)[1].lower()
    if ext == ".npy":
        try:
            import numpy as np
            arr = np.load(path)
            return {"embeddings": arr.tolist()}
        except ImportError:
            raise BlockDependencyError("numpy", install_hint="pip install numpy")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_chunks(raw):
    """Normalize chunk input into a list of dicts with at least a 'text' key."""
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, dict):
                out.append(item)
            elif isinstance(item, str):
                out.append({"text": item})
        return out
    if isinstance(raw, dict):
        # Format: {"chunks": [...]} or {"rows": [...]}
        for key in ("chunks", "rows", "data", "documents"):
            if key in raw and isinstance(raw[key], list):
                return _extract_chunks(raw[key])
    return []


def _extract_embeddings(raw):
    """Normalize embedding input into a list of float-vectors."""
    if isinstance(raw, dict):
        for key in ("embeddings", "vectors"):
            if key in raw and isinstance(raw[key], list):
                return raw[key]
    if isinstance(raw, list):
        if len(raw) > 0 and isinstance(raw[0], dict):
            return [item.get("embedding", item.get("vector", [])) for item in raw]
        if len(raw) > 0 and isinstance(raw[0], list):
            return raw
    return []


def _chroma_metric(distance_metric):
    """Map config metric name to ChromaDB's expected string."""
    return {"cosine": "cosine", "l2": "l2", "ip": "ip"}.get(distance_metric, "cosine")


def _faiss_index_type(distance_metric, dim):
    """Create a FAISS index for the given metric and dimension."""
    import faiss

    if distance_metric == "ip":
        return faiss.IndexFlatIP(dim)
    elif distance_metric == "cosine":
        # Normalize vectors then use inner-product for cosine
        return faiss.IndexFlatIP(dim)
    else:  # l2
        return faiss.IndexFlatL2(dim)


def _build_chroma(ctx, chunks, embeddings, collection_name, distance_metric, batch_size, overwrite=True):
    """Build a ChromaDB persistent vector store."""
    import chromadb

    db_path = os.path.join(ctx.run_dir, "chroma_db")
    client = chromadb.PersistentClient(path=db_path)

    metric = _chroma_metric(distance_metric)

    if overwrite:
        try:
            client.delete_collection(name=collection_name)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": metric},
    )

    documents = []
    metadatas = []
    ids = []
    emb_list = []
    has_precomputed = len(embeddings) == len(chunks)

    for i, chunk in enumerate(chunks):
        documents.append(chunk.get("text", ""))
        meta = {k: str(v) for k, v in chunk.items() if k != "text" and isinstance(v, (str, int, float, bool))}
        metadatas.append(meta if meta else {"index": str(i)})
        ids.append(chunk.get("chunk_id", chunk.get("id", str(i))))
        if has_precomputed:
            emb_list.append(embeddings[i])

    total = len(documents)
    inserted = 0
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        kwargs = {
            "documents": documents[start:end],
            "metadatas": metadatas[start:end],
            "ids": ids[start:end],
        }
        if has_precomputed:
            kwargs["embeddings"] = emb_list[start:end]
        collection.add(**kwargs)
        inserted += end - start
        ctx.report_progress(inserted, total)

    return {
        "type": "chroma",
        "path": db_path,
        "collection_name": collection_name,
        "distance_metric": metric,
        "count": collection.count(),
    }


def _build_faiss(ctx, chunks, embeddings, collection_name, distance_metric, batch_size):
    """Build a FAISS vector index."""
    import faiss
    try:
        import numpy as np
    except ImportError as e:
        from backend.block_sdk.exceptions import BlockDependencyError
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install numpy",
        )

    if not embeddings:
        raise BlockInputError(
            "FAISS requires pre-computed embeddings. Connect an Embedding Generator "
            "to the 'Pre-computed Embeddings' input port, or switch to ChromaDB "
            "(which can embed internally).",
            recoverable=False
        )

    dim = len(embeddings[0])
    vectors = np.array(embeddings, dtype=np.float32)

    if distance_metric == "cosine":
        # Normalize for cosine similarity via inner-product
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vectors = vectors / norms

    index = _faiss_index_type(distance_metric, dim)

    total = len(vectors)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        index.add(vectors[start:end])
        ctx.report_progress(end, total)

    index_path = os.path.join(ctx.run_dir, "faiss_index.bin")
    faiss.write_index(index, index_path)

    # Save chunk metadata alongside the index
    meta_path = os.path.join(ctx.run_dir, "faiss_metadata.json")
    metadata = []
    for i, chunk in enumerate(chunks):
        entry = {"index": i}
        entry.update({k: v for k, v in chunk.items() if k != "text"})
        entry["text_preview"] = chunk.get("text", "")[:200]
        metadata.append(entry)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return {
        "type": "faiss",
        "index_path": index_path,
        "metadata_path": meta_path,
        "collection_name": collection_name,
        "distance_metric": distance_metric,
        "dimension": dim,
        "count": int(index.ntotal),
    }


def run(ctx):
    store_type = ctx.config.get("store_type", "chroma")
    collection_name = ctx.config.get("collection_name", "blueprint_rag")
    distance_metric = ctx.config.get("distance_metric", "cosine")
    batch_size = int(ctx.config.get("batch_size", 256))
    overwrite = ctx.config.get("overwrite", True)

    # ── Load chunks ──────────────────────────────────────────────
    raw_chunks = ctx.load_input("chunks")
    if isinstance(raw_chunks, str):
        raw_chunks = _load_json(raw_chunks)
    chunks = _extract_chunks(raw_chunks)

    if not chunks:
        raise BlockInputError(
            "No text chunks received on the 'chunks' input port. "
            "Connect a Text Chunker or dataset upstream.",
            recoverable=False
        )

    ctx.log_message(f"Received {len(chunks)} chunks")

    # ── Load pre-computed embeddings (optional) ──────────────────
    embeddings = []
    raw_emb = ctx.load_input("embeddings") if ctx.inputs.get("embeddings") else None
    if raw_emb is not None:
        if isinstance(raw_emb, str):
            raw_emb = _load_json(raw_emb)
        embeddings = _extract_embeddings(raw_emb)
        if embeddings:
            ctx.log_message(f"Using {len(embeddings)} pre-computed embeddings (dim={len(embeddings[0])})")
        else:
            ctx.log_message("Embeddings input connected but empty — will embed internally")

    # ── Build the vector store ───────────────────────────────────
    ctx.log_message(f"Building {store_type.upper()} store '{collection_name}' (metric={distance_metric})...")

    store_config = None

    if store_type == "faiss":
        try:
            store_config = _build_faiss(
                ctx, chunks, embeddings, collection_name, distance_metric, batch_size
            )
        except ImportError:
            raise BlockDependencyError("faiss-cpu", install_hint="pip install faiss-cpu")
    else:
        # Default: ChromaDB
        try:
            store_config = _build_chroma(
                ctx, chunks, embeddings, collection_name, distance_metric, batch_size, overwrite
            )
        except ImportError:
            raise BlockDependencyError("chromadb", install_hint="pip install chromadb")

    # ── Save store config output ─────────────────────────────────
    config_path = os.path.join(ctx.run_dir, "store_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(store_config, f, indent=2)
    ctx.save_output("store_config", config_path)

    # ── Save indexing metrics ────────────────────────────────────
    stats = {
        "store_type": store_type,
        "collection_name": collection_name,
        "distance_metric": distance_metric,
        "total_chunks_indexed": store_config.get("count", len(chunks)),
        "embedding_dimension": store_config.get("dimension", len(embeddings[0]) if embeddings else 0),
        "used_precomputed_embeddings": len(embeddings) > 0,
        "batch_size": batch_size,
    }
    stats_path = os.path.join(ctx.run_dir, "indexing_stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    ctx.save_output("metrics", stats_path)

    ctx.log_metric("chunks_indexed", store_config.get("count", len(chunks)))
    ctx.log_message(
        f"Done — indexed {store_config.get('count', len(chunks))} vectors "
        f"into {store_type.upper()} ({distance_metric})"
    )
