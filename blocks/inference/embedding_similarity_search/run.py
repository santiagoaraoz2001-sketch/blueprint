"""Embedding Similarity Search — find nearest neighbors using cosine, dot-product, or euclidean similarity.

Workflows:
  1. Semantic search: query text -> embed -> search corpus -> ranked results
  2. RAG retrieval: user question -> embed -> find relevant chunks -> LLM context
  3. Deduplication: document -> embed -> find near-duplicates in corpus
  4. Recommendation: item embedding -> find similar items -> recommendations
  5. Evaluation: test queries -> search -> measure retrieval quality
"""

import json
import math
import os


def _load_json(path):
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _extract_vectors_and_labels(raw, embedding_column="_embedding"):
    """Parse flexible embedding formats into (vectors, labels, metadata_rows)."""
    if raw is None:
        return [], [], []

    if isinstance(raw, dict):
        vectors = raw.get("embeddings", raw.get("vectors", []))
        labels = raw.get("labels", raw.get("ids", list(range(len(vectors)))))
        return vectors, labels, []

    if isinstance(raw, list):
        if not raw:
            return [], [], []
        if isinstance(raw[0], dict):
            vectors = []
            labels = []
            metadata = []
            for i, item in enumerate(raw):
                emb = item.get(embedding_column, item.get("embedding", item.get("vector", item.get("_embedding", []))))
                vectors.append(emb)
                labels.append(item.get("label", item.get("id", item.get("text", i))))
                metadata.append(item)
            return vectors, labels, metadata
        if isinstance(raw[0], (list, tuple)):
            return raw, list(range(len(raw))), []
        if isinstance(raw[0], (int, float)):
            return [raw], [0], []

    return [], [], []


def _load_metadata(ctx):
    """Load metadata from the metadata input port."""
    if not ctx.inputs.get("metadata"):
        return []
    try:
        raw = ctx.load_input("metadata")
    except Exception:
        return []
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = _load_json(raw)
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("rows", "data", "chunks", "documents"):
            if key in raw and isinstance(raw[key], list):
                return raw[key]
    return []


def _cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _dot_product(a, b):
    return sum(x * y for x, y in zip(a, b))


def _euclidean_similarity(a, b):
    dist = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    return 1.0 / (1.0 + dist)


def run(ctx):
    top_k = int(ctx.config.get("top_k", 10))
    metric = ctx.config.get("metric", "cosine")
    threshold = float(ctx.config.get("threshold", 0.0))
    include_metadata = ctx.config.get("include_metadata", True)
    exclude_self = ctx.config.get("exclude_self", False)
    embedding_column = ctx.config.get("embedding_column", "_embedding")
    sort_order = ctx.config.get("sort_order", "descending")
    include_vectors = ctx.config.get("include_vectors", False)
    normalize_embeddings = ctx.config.get("normalize_embeddings", False)
    dataset_format = ctx.config.get("dataset_format", "json")
    if isinstance(normalize_embeddings, str):
        normalize_embeddings = normalize_embeddings.lower() in ("true", "1", "yes")

    # ── Load corpus embeddings (from embeddings or dataset input) ──
    vectors = []
    labels = []
    dataset_metadata = []

    # Try dataset input first (from embedding_generator output)
    if ctx.inputs.get("dataset"):
        try:
            ds_path = ctx.load_input("dataset")
            data_file = os.path.join(ds_path, "data.json") if os.path.isdir(ds_path) else ds_path
            with open(data_file, "r", encoding="utf-8") as f:
                rows = json.load(f)
            vectors, labels, dataset_metadata = _extract_vectors_and_labels(rows, embedding_column)
            if vectors:
                ctx.log_message(f"Loaded {len(vectors)} embeddings from dataset")
        except Exception as e:
            ctx.log_message(f"Dataset load error: {e}")

    # Fall back to embeddings input
    if not vectors and ctx.inputs.get("embeddings"):
        raw_emb = ctx.load_input("embeddings")
        if isinstance(raw_emb, str):
            raw_emb = _load_json(raw_emb)
        vectors, labels, dataset_metadata = _extract_vectors_and_labels(raw_emb, embedding_column)

    if not vectors:
        raise ValueError("No embeddings received. Connect 'dataset' or 'embeddings' input.")

    # Filter out empty vectors
    valid_indices = [i for i, v in enumerate(vectors) if v and len(v) > 0]
    if len(valid_indices) < len(vectors):
        ctx.log_message(f"Filtered {len(vectors) - len(valid_indices)} empty embeddings")
        vectors = [vectors[i] for i in valid_indices]
        labels = [labels[i] for i in valid_indices] if labels else list(range(len(vectors)))
        dataset_metadata = [dataset_metadata[i] for i in valid_indices] if dataset_metadata else []

    dim = len(vectors[0])

    # L2-normalize if requested
    if normalize_embeddings:
        for i in range(len(vectors)):
            norm = math.sqrt(sum(v * v for v in vectors[i])) or 1.0
            vectors[i] = [v / norm for v in vectors[i]]
        ctx.log_message("Corpus embeddings L2-normalized")

    ctx.log_message(f"Corpus: {len(vectors)} embeddings (dim={dim})")

    # ── Load query embedding(s) ──────────────────────────────────
    query_vectors = []
    query_labels = []

    if ctx.inputs.get("query"):
        raw_query = ctx.load_input("query")
        if isinstance(raw_query, str):
            raw_query = _load_json(raw_query)
        query_vectors, query_labels, _ = _extract_vectors_and_labels(raw_query, embedding_column)

    if not query_vectors:
        query_vectors = [vectors[0]]
        query_labels = [labels[0] if labels else 0]
        ctx.log_message("No query provided — using first corpus embedding as query")
    else:
        if normalize_embeddings:
            for i in range(len(query_vectors)):
                norm = math.sqrt(sum(v * v for v in query_vectors[i])) or 1.0
                query_vectors[i] = [v / norm for v in query_vectors[i]]
        ctx.log_message(f"Query: {len(query_vectors)} vector(s)")

    # ── Load metadata (from metadata input or dataset_metadata) ──
    metadata_rows = []
    if include_metadata:
        metadata_rows = _load_metadata(ctx)
        if not metadata_rows and dataset_metadata:
            metadata_rows = dataset_metadata
        if metadata_rows:
            ctx.log_message(f"Metadata: {len(metadata_rows)} rows")

    # ── Select similarity function ───────────────────────────────
    sim_fn = {
        "cosine": _cosine_similarity,
        "dot_product": _dot_product,
        "euclidean": _euclidean_similarity,
    }.get(metric, _cosine_similarity)

    # ── Search ───────────────────────────────────────────────────
    all_results = []
    total_queries = len(query_vectors)

    for qi, query_vec in enumerate(query_vectors):
        scored = []
        for ci, corpus_vec in enumerate(vectors):
            score = sim_fn(query_vec, corpus_vec)

            if exclude_self and score >= 0.999999:
                continue
            if score < threshold:
                continue

            result = {
                "query_index": qi,
                "rank": 0,
                "index": ci,
                "label": str(labels[ci]) if ci < len(labels) else str(ci),
                "score": round(score, 6),
            }

            # Attach metadata
            if include_metadata and ci < len(metadata_rows):
                meta = metadata_rows[ci]
                if isinstance(meta, dict):
                    for key, val in meta.items():
                        if key not in result and key != embedding_column:
                            result[key] = val

            # Attach embedding vector
            if include_vectors:
                result["_embedding"] = vectors[ci]

            scored.append(result)

        scored.sort(key=lambda x: x["score"], reverse=(sort_order == "descending"))
        scored = scored[:top_k]
        for rank, r in enumerate(scored):
            r["rank"] = rank + 1

        all_results.extend(scored)
        ctx.report_progress(qi + 1, total_queries)

    # For single-query, drop the query_index field
    if total_queries == 1:
        for r in all_results:
            del r["query_index"]

    ctx.log_message(f"Found {len(all_results)} results (top-{top_k}, metric={metric})")

    # ── Save results ─────────────────────────────────────────────
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    if dataset_format == "jsonl":
        out_path = os.path.join(out_dir, "data.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for row in all_results:
                f.write(json.dumps(row) + "\n")
    elif dataset_format == "csv":
        import csv
        out_path = os.path.join(out_dir, "data.csv")
        if all_results:
            keys = list(all_results[0].keys())
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(all_results)
        else:
            with open(out_path, "w") as f:
                f.write("")
    else:
        out_path = os.path.join(out_dir, "data.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2)
    ctx.save_output("dataset", out_dir)

    # ── Save stats ───────────────────────────────────────────────
    best_score = max((r["score"] for r in all_results), default=0.0)
    worst_score = min((r["score"] for r in all_results), default=0.0)
    avg_score = sum(r["score"] for r in all_results) / len(all_results) if all_results else 0.0

    stats = {
        "total_corpus_embeddings": len(vectors),
        "embedding_dimension": dim,
        "num_queries": total_queries,
        "metric": metric,
        "top_k": top_k,
        "threshold": threshold,
        "results_returned": len(all_results),
        "best_score": round(best_score, 6),
        "worst_score": round(worst_score, 6),
        "avg_score": round(avg_score, 6),
        "metadata_attached": include_metadata and len(metadata_rows) > 0,
    }
    ctx.save_output("metrics", stats)

    ctx.log_metric("results_returned", len(all_results))
    ctx.log_metric("best_score", round(best_score, 6))
