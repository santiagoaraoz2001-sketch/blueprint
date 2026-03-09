"""Retrieval Agent — searches vector store and generates LLM responses (RAG)."""

import json
import os
import time


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
    provider = ctx.config.get("provider", "ollama")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")

    if isinstance(include_sources, str):
        include_sources = include_sources.lower() in ("true", "1", "yes")
    if isinstance(rerank, str):
        rerank = rerank.lower() in ("true", "1", "yes")

    # ── Load model info ─────────────────────────────────────────────────
    model_name = ctx.config.get("model_name", "")
    try:
        model_info = ctx.load_input("model")
        if isinstance(model_info, dict):
            model_name = model_name or model_info.get(
                "model_name", model_info.get("model_id", "")
            )
            provider = model_info.get("source", provider)
            endpoint = model_info.get("endpoint", endpoint)
        elif isinstance(model_info, str):
            model_name = model_name or model_info
    except (ValueError, Exception):
        pass

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

        final_text = _generate(
            provider, endpoint, model_name, prompt, max_tokens, temperature,
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

    # ── Save text response ───────────────────────────────────────────
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
        "provider": provider,
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

    # No store connected — return empty
    return []


def _simple_rerank(docs, query):
    """Simple keyword-overlap reranking."""
    query_words = set(query.lower().split())

    def relevance(doc):
        doc_words = set(doc.lower().split())
        return len(query_words & doc_words)

    return sorted(docs, key=relevance, reverse=True)


# ── Generation ──────────────────────────────────────────────────────────


def _generate(provider, endpoint, model_name, prompt, max_tokens, temperature=0.3):
    """Generate a response using the configured provider."""
    if not model_name:
        # Fallback: try transformers pipeline
        try:
            from transformers import pipeline
            generator = pipeline("text-generation", model="gpt2", device=-1)
            out = generator(prompt, max_new_tokens=min(max_tokens, 100), num_return_sequences=1)
            return out[0]["generated_text"].replace(prompt, "").strip()
        except ImportError:
            pass

        time.sleep(0.5)
        return (
            f"[Simulated RAG Response] Based on the retrieved context, "
            f"the answer is synthesized from the relevant documents."
        )

    import urllib.request

    if provider == "ollama":
        url = f"{endpoint.rstrip('/')}/api/generate"
        payload = json.dumps({
            "model": model_name,
            "prompt": prompt,
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode()).get("response", "")
        except Exception as e:
            return f"[Generation error: {e}]"

    if provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        payload = json.dumps({
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[Generation error: {e}]"

    if provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        payload = json.dumps({
            "model": model_name,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
            "anthropic-version": "2023-06-01",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                return data["content"][0]["text"]
        except Exception as e:
            return f"[Generation error: {e}]"

    return f"[Unsupported provider: {provider}]"
