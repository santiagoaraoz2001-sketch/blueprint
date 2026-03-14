"""RAG Pipeline — Retrieval-Augmented Generation with context retrieval and answer generation.

Workflows:
  1. Q&A over documents: knowledge base -> retrieve relevant chunks -> LLM answer
  2. Support chatbot: FAQ dataset -> RAG -> contextual answers
  3. Research assistant: paper chunks -> query -> synthesized answer
  4. Code documentation: docstrings dataset -> question -> relevant code + explanation
  5. Knowledge grounding: facts dataset -> claim -> grounded response
"""

import json
import os
import time
import math


def run(ctx):
    # Read upstream dataset metadata
    _dataset_meta = {}
    try:
        _meta_input = ctx.load_input("dataset_meta")
        if isinstance(_meta_input, dict):
            _dataset_meta = _meta_input
    except (ValueError, KeyError):
        pass

    query = ctx.config.get("query", "")
    text_column = _dataset_meta.get("text_column", ctx.config.get("text_column", "text"))
    top_k = int(ctx.config.get("top_k", 5))
    # ── Model config: upstream model input takes priority ──────────────
    model_data = {}
    if ctx.inputs.get("model"):
        model_data = ctx.load_input("model")
        if isinstance(model_data, dict):
            ctx.log_message(f"Using connected model: {model_data.get('model_name', 'unknown')}")

    provider = model_data.get("source", model_data.get("backend",
        ctx.config.get("backend", ctx.config.get("provider", "ollama"))))
    model_name = model_data.get("model_name", model_data.get("model_id",
        ctx.config.get("model_name", "llama3.2")))
    endpoint = model_data.get("endpoint", model_data.get("base_url",
        ctx.config.get("endpoint", "http://localhost:11434")))
    api_key = model_data.get("api_key",
        ctx.config.get("api_key", ""))

    # Config conflict warnings
    if ctx.inputs.get("model") and ctx.config.get("model_name"):
        ctx.log_message(
            f"\u26a0 Config conflict: upstream model='{model_data.get('model_name')}' "
            f"but local config has model_name='{ctx.config.get('model_name')}'. "
            f"Using upstream. Clear local config to remove this warning."
        )

    temperature = float(ctx.config.get("temperature", 0.3))
    max_tokens = int(ctx.config.get("max_tokens", 512))
    system_prompt = ctx.config.get("system_prompt", "")

    if not model_name:
        raise ValueError("model_name is required — set it in config or connect a model input.")

    if not query:
        raise ValueError("query is required — set it in the config.")

    # Load knowledge base
    kb_data = ctx.resolve_as_file_path("dataset")
    rows = _load_dataset(kb_data)
    if not rows:
        raise ValueError("Knowledge base is empty or could not be loaded.")

    ctx.log_message(f"RAG Pipeline: {len(rows)} chunks, query: {query[:100]}...")
    ctx.log_message(f"Model: {model_name} ({provider}), top_k={top_k}")
    ctx.report_progress(0, 3)

    # Step 1: Retrieve relevant chunks using TF-IDF-like scoring
    retrieval_start = time.time()
    chunks_with_scores = _retrieve_chunks(query, rows, text_column, top_k)
    retrieval_elapsed = time.time() - retrieval_start

    ctx.log_message(f"Retrieved {len(chunks_with_scores)} chunks in {retrieval_elapsed:.3f}s")
    ctx.report_progress(1, 3)

    # Build context from retrieved chunks
    context_parts = []
    context_chunks = []
    for rank, (text, score, idx, source) in enumerate(chunks_with_scores):
        context_parts.append(f"[Chunk {rank+1}] {text}")
        chunk_row = {
            "text": text,
            "score": round(score, 4),
            "index": idx,
        }
        if source:
            chunk_row["source"] = source
        context_chunks.append(chunk_row)

    context_text = "\n\n".join(context_parts)
    total_context_chars = len(context_text)

    # Step 2: Generate answer
    generation_start = time.time()
    prompt = f"Context:\n{context_text}\n\nQuestion: {query}\n\nAnswer:"

    try:
        answer = _call_llm(provider, endpoint, api_key, model_name, prompt, system_prompt, temperature, max_tokens)
    except Exception as e:
        ctx.log_message(f"Generation error: {e}")
        raise

    generation_elapsed = time.time() - generation_start
    total_elapsed = retrieval_elapsed + generation_elapsed

    ctx.log_message(f"Generated answer in {generation_elapsed:.3f}s ({len(answer)} chars)")
    ctx.report_progress(2, 3)

    # Save answer output
    output_format = ctx.config.get("output_format", "text")
    if output_format == "json":
        output_obj = {
            "answer": answer,
            "query": query,
            "model": model_name,
            "provider": provider,
            "num_chunks_used": len(context_chunks),
            "elapsed_s": round(total_elapsed, 3),
        }
        answer_text = json.dumps(output_obj, indent=2)
        out_path = os.path.join(ctx.run_dir, "answer.json")
    else:
        answer_text = answer
        out_path = os.path.join(ctx.run_dir, "answer.txt")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(answer_text)
    ctx.save_output("text", out_path)

    # Save context chunks dataset with format support
    dataset_format = ctx.config.get("dataset_format", "json")
    if dataset_format == "jsonl":
        chunks_path = os.path.join(ctx.run_dir, "results.jsonl")
        with open(chunks_path, "w", encoding="utf-8") as f:
            for row in context_chunks:
                f.write(json.dumps(row) + "\n")
    elif dataset_format == "csv":
        import csv as _csv
        chunks_path = os.path.join(ctx.run_dir, "results.csv")
        if context_chunks:
            keys = list(context_chunks[0].keys())
            with open(chunks_path, "w", newline="", encoding="utf-8") as f:
                writer = _csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(context_chunks)
        else:
            with open(chunks_path, "w") as f:
                f.write("")
    else:
        chunks_path = os.path.join(ctx.run_dir, "results.json")
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(context_chunks, f, indent=2)
    ctx.save_output("dataset", chunks_path)

    # Save metrics
    metrics = {
        "query": query,
        "model": model_name,
        "provider": provider,
        "num_chunks_retrieved": len(context_chunks),
        "num_chunks_used": len(context_chunks),
        "total_context_chars": total_context_chars,
        "answer_length": len(answer),
        "retrieval_elapsed_s": round(retrieval_elapsed, 3),
        "generation_elapsed_s": round(generation_elapsed, 3),
        "total_elapsed_s": round(total_elapsed, 3),
    }
    ctx.save_output("metrics", metrics)
    ctx.log_metric("total_elapsed_s", metrics["total_elapsed_s"])
    ctx.log_metric("num_chunks_retrieved", metrics["num_chunks_retrieved"])
    ctx.log_metric("answer_length", metrics["answer_length"])
    ctx.log_message(f"RAG complete: {len(context_chunks)} chunks, {len(answer)} char answer")
    ctx.report_progress(3, 3)


def _load_dataset(data):
    if isinstance(data, list):
        return data
    if isinstance(data, str):
        path = os.path.join(data, "data.json") if os.path.isdir(data) else data
        if os.path.isfile(path):
            with open(path, "r") as f:
                return json.load(f)
    return []


def _retrieve_chunks(query, rows, text_column, top_k):
    """Simple TF-IDF-like retrieval using term frequency overlap."""
    query_terms = set(query.lower().split())
    if not query_terms:
        return []

    scored = []
    for idx, row in enumerate(rows):
        if isinstance(row, dict):
            text = str(row.get(text_column, row.get("text", row.get("content", ""))))
            source = row.get("source", row.get("file", ""))
        else:
            text = str(row)
            source = ""

        if not text:
            continue

        # Compute simple term overlap score
        doc_terms = text.lower().split()
        doc_term_set = set(doc_terms)
        if not doc_term_set:
            continue

        # Term frequency based scoring
        overlap = query_terms & doc_term_set
        if not overlap:
            continue

        # Score: proportion of query terms found * log-inverse doc length (prefer concise)
        term_coverage = len(overlap) / len(query_terms)
        # Frequency boost: count how many times query terms appear
        freq_count = sum(1 for t in doc_terms if t in query_terms)
        freq_score = freq_count / len(doc_terms)
        # Combined score
        score = (term_coverage * 0.7) + (freq_score * 0.3)

        scored.append((text, score, idx, source))

    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def _call_llm(provider, endpoint, api_key, model, prompt, system_prompt, temperature, max_tokens):
    import urllib.request

    if provider == "ollama":
        url = f"{endpoint.rstrip('/')}/api/generate"
        payload = {
            "model": model, "prompt": prompt, "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system_prompt:
            payload["system"] = system_prompt
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode()).get("response", "")

    elif provider == "mlx":
        try:
            from mlx_lm import load, generate
        except ImportError:
            raise RuntimeError("mlx-lm not installed. Run: pip install mlx-lm")
        model_obj, tokenizer = load(model)
        return generate(model_obj, tokenizer, prompt=prompt, max_tokens=max_tokens, temp=temperature)

    elif provider == "openai":
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OpenAI API key required.")
        url = endpoint.rstrip("/")
        if "/v1/" not in url:
            url = f"{url}/v1/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        body = {"model": model, "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens}
        payload = json.dumps(body).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode())["choices"][0]["message"]["content"]

    elif provider == "anthropic":
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("Anthropic API key required.")
        url = endpoint.rstrip("/")
        if not url.endswith("/v1/messages"):
            url = f"{url}/v1/messages"
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
                   "temperature": temperature, "max_tokens": max_tokens}
        if system_prompt:
            payload["system"] = system_prompt
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode())["content"][0]["text"]

    else:
        raise ValueError(f"Unknown provider: {provider}")
