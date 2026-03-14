"""Reranker — re-rank search results using a cross-encoder model.

Workflows:
  1. RAG reranking: retriever results + query -> reranked -> top-k to LLM
  2. Search quality: initial search -> rerank with cross-encoder -> better results
  3. Document ranking: candidate docs + query -> relevance-sorted list
  4. Multi-stage retrieval: sparse retrieval -> dense reranking -> final results
  5. Result filtering: search results -> rerank -> threshold filter
"""

import json
import os

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


def run(ctx):
    dataset_input = ctx.resolve_as_file_path("dataset")

    # Read upstream dataset metadata
    _dataset_meta = {}
    try:
        _meta_input = ctx.load_input("dataset_meta")
        if isinstance(_meta_input, dict):
            _dataset_meta = _meta_input
    except (ValueError, KeyError):
        pass

    model_name = ctx.config.get("model_name", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    query_column = ctx.config.get("query_column", "query")
    text_column = _dataset_meta.get("text_column", ctx.config.get("text_column", "text"))
    top_k = int(ctx.config.get("top_k", 10))
    score_column = ctx.config.get("score_column", "_rerank_score")
    score_threshold = float(ctx.config.get("score_threshold", 0.0))
    batch_size = int(ctx.config.get("batch_size", 64))
    dataset_format = ctx.config.get("dataset_format", "json")

    # Load dataset
    if isinstance(dataset_input, str):
        data_file = os.path.join(dataset_input, "data.json") if os.path.isdir(dataset_input) else dataset_input
        with open(data_file, "r") as f:
            rows = json.load(f)
    elif isinstance(dataset_input, list):
        rows = dataset_input
    else:
        raise BlockDataError("Invalid dataset input")

    # Load query from input or from dataset rows
    query = ""
    if ctx.inputs.get("query"):
        query_data = ctx.load_input("query")
        if isinstance(query_data, str):
            if os.path.isfile(query_data):
                with open(query_data, "r", encoding="utf-8", errors="ignore") as f:
                    query = f.read().strip()
            else:
                query = query_data

    ctx.log_message(f"Reranking {len(rows)} items with model: {model_name}")
    ctx.report_progress(0, 2)

    # Extract passages
    passages = []
    queries = []
    for row in rows:
        if isinstance(row, dict):
            passages.append(str(row.get(text_column, "")))
            queries.append(query or str(row.get(query_column, "")))
        else:
            passages.append(str(row))
            queries.append(query)

    # Compute scores
    use_real_model = False
    scores = []

    try:
        from sentence_transformers import CrossEncoder
        ctx.log_message("Loading CrossEncoder model...")
        model = CrossEncoder(model_name)
        use_real_model = True
        ctx.log_message("CrossEncoder loaded.")

        # Build pairs and predict in batches
        pairs = list(zip(queries, passages))
        batch_scores = model.predict(pairs, batch_size=batch_size)
        scores = [float(s) for s in batch_scores]

    except ImportError as e:
        from backend.block_sdk.exceptions import BlockDependencyError
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install sentence-transformers",
        )

    ctx.report_progress(1, 2)

    # Attach scores and sort
    results = []
    for i, row in enumerate(rows):
        entry = dict(row) if isinstance(row, dict) else {"text": str(row)}
        entry[score_column] = round(scores[i], 6) if i < len(scores) else 0.0
        results.append(entry)

    results.sort(key=lambda x: x.get(score_column, 0), reverse=True)

    # Apply score threshold filter
    if score_threshold > 0:
        before_count = len(results)
        results = [r for r in results if r.get(score_column, 0) >= score_threshold]
        if len(results) < before_count:
            ctx.log_message(f"Filtered {before_count - len(results)} items below threshold {score_threshold}")

    if 0 < top_k < len(results):
        results = results[:top_k]

    for i, entry in enumerate(results):
        entry["_rank"] = i + 1

    # Save
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    if dataset_format == "jsonl":
        out_path = os.path.join(out_dir, "data.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for row in results:
                f.write(json.dumps(row) + "\n")
    elif dataset_format == "csv":
        import csv
        out_path = os.path.join(out_dir, "data.csv")
        if results:
            keys = list(results[0].keys())
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(results)
        else:
            with open(out_path, "w") as f:
                f.write("")
    else:
        out_path = os.path.join(out_dir, "data.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

    ctx.save_output("dataset", out_dir)
    ctx.save_output("metrics", {
        "total_items": len(rows),
        "reranked_items": len(results),
        "top_score": results[0][score_column] if results else 0,
        "model": model_name,
        "used_real_model": use_real_model,
    })
    ctx.log_metric("reranked_items", len(results))
    ctx.log_message(f"Reranking complete: {len(results)} items returned")
    ctx.report_progress(2, 2)
