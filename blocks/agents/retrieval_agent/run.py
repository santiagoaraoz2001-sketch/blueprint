"""Retrieval Agent — searches vector store and generates LLM responses (RAG).

Uses connected LLM Inference block for all model calls via shared utilities.
"""

import json
import os
import time

from blocks.inference._inference_utils import call_inference

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
    # ── Config ──────────────────────────────────────────────────────────
    top_k = int(ctx.config.get("top_k", 5))
    rerank = ctx.config.get("rerank", False)
    max_tokens = int(ctx.config.get("max_tokens", 1024))
    prompt_template = ctx.config.get(
        "prompt_template",
        "Context:\n{context}\n\nQuestion: {query}\n\nAnswer based on the context above:",
    )
    temperature = float(ctx.config.get("temperature", 0.3))
    include_sources = ctx.config.get("include_sources", False)

    if isinstance(include_sources, str):
        include_sources = include_sources.lower() in ("true", "1", "yes")
    if isinstance(rerank, str):
        rerank = rerank.lower() in ("true", "1", "yes")

    # ── Load LLM config — accept llm port OR model port ───────────────
    llm_config = None
    model_name = ""
    framework = ""
    inf_config = {}

    # Try llm port first (preferred — contains framework + config)
    try:
        llm_data = ctx.load_input("llm")
        if isinstance(llm_data, dict):
            if "framework" in llm_data:
                framework = llm_data.get("framework", "ollama")
                model_name = llm_data.get("model", "")
                inf_config = dict(llm_data.get("config") or {})
                llm_config = llm_data
            elif "model_name" in llm_data or "model_id" in llm_data:
                model_name = llm_data.get("model_name", llm_data.get("model_id", ""))
                framework = llm_data.get("source", llm_data.get("backend", "ollama"))
                inf_config = {"endpoint": llm_data.get("endpoint", "http://localhost:11434")}
                llm_config = {"framework": framework, "model": model_name, "config": inf_config}
    except (ValueError, Exception):
        pass

    # Try model port as fallback (direct model_selector connection)
    if not model_name:
        try:
            model_data = ctx.load_input("model")
            if isinstance(model_data, dict):
                model_name = model_data.get("model_name", model_data.get("model_id", ""))
                framework = model_data.get("source", model_data.get("backend", "ollama"))
                inf_config = {"endpoint": model_data.get("endpoint", "http://localhost:11434")}
                llm_config = {"framework": framework, "model": model_name, "config": inf_config}
            elif isinstance(model_data, str):
                model_name = model_data
                framework = "ollama"
                llm_config = {"framework": framework, "model": model_name, "config": {}}
        except (ValueError, Exception):
            pass

    # Apply per-block config overrides
    inf_config["max_tokens"] = max_tokens
    inf_config["temperature"] = temperature

    use_real = bool(llm_config and model_name)

    # ── Load vector store config ────────────────────────────────────────
    vstore = {}
    try:
        store_data = ctx.load_input("store")
        if isinstance(store_data, str) and os.path.isfile(store_data):
            with open(store_data, "r") as f:
                vstore = json.load(f)
        elif isinstance(store_data, dict):
            vstore = store_data
    except (ValueError, Exception):
        pass

    # ── Load queries ────────────────────────────────────────────────────
    queries = []
    try:
        queries_data = ctx.load_input("dataset")
        if isinstance(queries_data, str) and os.path.isdir(queries_data):
            data_file = os.path.join(queries_data, "data.json")
            if os.path.isfile(data_file):
                with open(data_file, "r") as f:
                    queries = json.load(f)
        elif isinstance(queries_data, str) and os.path.isfile(queries_data):
            with open(queries_data, "r") as f:
                queries = json.load(f)
        elif isinstance(queries_data, list):
            queries = queries_data
    except (ValueError, Exception):
        pass

    # ── Load single query from text input ────────────────────────────────
    try:
        query_data = ctx.load_input("query")
        if isinstance(query_data, str):
            qt = query_data if not os.path.isfile(query_data) else open(query_data).read()
        elif isinstance(query_data, dict):
            qt = query_data.get("text", query_data.get("query", ""))
        else:
            qt = ""
        if qt:
            queries = [{"id": 0, "query": qt}]
    except (ValueError, Exception):
        pass

    if not queries:
        ctx.log_message("No queries connected. Using demo query.")
        queries = [{"id": 0, "query": "What is ChromaDB used for?"}]

    ctx.log_message(f"RAG Agent: {len(queries)} queries, top_k={top_k}, rerank={rerank}")
    if not use_real:
        ctx.log_message("No model connected. Running in demo mode. "
                        "Connect a Model Selector or LLM Inference block for real output.")

    # ── Process queries ─────────────────────────────────────────────────
    responses = []
    total_retrieved = 0

    for idx, qdict in enumerate(queries):
        if isinstance(qdict, str):
            qdict = {"query": qdict}

        query_text = qdict.get("query", qdict.get("text", qdict.get("prompt", "")))
        if not query_text:
            continue

        ctx.log_message(f"Query {idx + 1}: '{query_text[:80]}'")

        # ── Retrieve documents ──────────────────────────────────────────
        context_docs = _retrieve(vstore, query_text, top_k)
        total_retrieved += len(context_docs)

        # ── Rerank if enabled ───────────────────────────────────────────
        if rerank and len(context_docs) > 1:
            context_docs = _simple_rerank(context_docs, query_text)

        # ── Build context string ────────────────────────────────────────
        context_block = "\n\n---\n\n".join(
            f"[Doc {i + 1}] {doc}" for i, doc in enumerate(context_docs)
        ) if context_docs else "[No documents retrieved]"

        # ── Generate response ───────────────────────────────────────────
        prompt = prompt_template.replace("{context}", context_block).replace("{query}", query_text)

        if use_real:
            try:
                final_text, _ = call_inference(
                    framework, model_name, prompt,
                    config=inf_config, log_fn=ctx.log_message,
                )
            except Exception as e:
                final_text = f"[Generation error: {e}]"
        else:
            time.sleep(0.5)
            final_text = (
                f"[Simulated RAG Response] Based on the retrieved context, "
                f"the answer is synthesized from the relevant documents."
            )

        if include_sources and context_docs:
            source_refs = "\n\nSources:\n" + "\n".join(
                f"- [Doc {i + 1}]: {doc[:100]}..." for i, doc in enumerate(context_docs)
            )
            final_text += source_refs

        responses.append({
            "id": qdict.get("id", idx),
            "query": query_text,
            "response": final_text,
            "context_retrieved": context_docs,
            "num_docs_retrieved": len(context_docs),
        })

        ctx.report_progress(idx + 1, len(queries))

    # ── Save outputs ────────────────────────────────────────────────────
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "data.json"), "w") as f:
        json.dump(responses, f, indent=2)
    ctx.save_output("dataset", out_dir)

    output_format = ctx.config.get("output_format", "plain")
    if output_format == "json":
        response_text = json.dumps(responses, indent=2)
    elif output_format == "markdown":
        parts = []
        for r in responses:
            parts.append(f"### {r['query']}\n\n{r['response']}")
            if r.get("context_retrieved"):
                parts.append("\n**Sources:**\n" + "\n".join(
                    f"- {doc[:100]}..." for doc in r["context_retrieved"]
                ))
        response_text = "\n\n".join(parts)
    else:
        if len(responses) == 1:
            response_text = responses[0]["response"]
        else:
            response_text = "\n\n---\n\n".join(
                f"Q: {r['query']}\nA: {r['response']}" for r in responses
            )

    response_path = os.path.join(ctx.run_dir, "response.txt")
    with open(response_path, "w") as f:
        f.write(response_text)
    ctx.save_output("response", response_path)

    avg_retrieved = total_retrieved / max(len(responses), 1)
    metrics = {
        "total_queries": len(responses),
        "avg_retrieved": round(avg_retrieved, 2),
        "top_k": top_k,
        "rerank_enabled": rerank,
        "model": model_name or "demo",
        "framework": framework or "demo",
    }
    ctx.save_output("metrics", metrics)
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_metric(k, v)

    ctx.log_message(f"RAG complete: {len(responses)} queries processed")
    ctx.report_progress(1, 1)


# ── Retrieval ───────────────────────────────────────────────────────────


def _retrieve(vstore, query_text, top_k):
    """Retrieve documents from the configured vector store."""
    store_type = vstore.get("type", "")

    if store_type == "chroma":
        try:
            import chromadb
            db_path = vstore.get("path")
            client = chromadb.PersistentClient(path=db_path)
            collection = client.get_collection(vstore.get("collection_name"))
            res = collection.query(query_texts=[query_text], n_results=top_k)
            if res and res.get("documents"):
                return res["documents"][0]
        except Exception as e:
            return [f"[ChromaDB retrieval error: {e}]"]

    if store_type == "simulated":
        chunks = vstore.get("simulated_chunks", [])
        return [c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in chunks[:top_k]]

    return []


def _simple_rerank(docs, query):
    """Simple keyword-overlap reranking."""
    query_words = set(query.lower().split())
    def relevance(doc):
        doc_words = set(doc.lower().split())
        return len(query_words & doc_words)
    return sorted(docs, key=relevance, reverse=True)
