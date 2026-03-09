"""Text Chunker — splits documents into smaller semantic pieces."""

import json
import os

RECURSIVE_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _chunk_recursive(text, chunk_size, overlap, separators=None):
    """Recursively split text using a hierarchy of separators."""
    if separators is None:
        separators = list(RECURSIVE_SEPARATORS)
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    separator = separators[0] if separators else ""
    remaining_seps = separators[1:] if len(separators) > 1 else [""]

    if not separator:
        # Character-level base case
        return _chunk_character(text, chunk_size, overlap)

    parts = text.split(separator)
    chunks = []
    current = ""

    for part in parts:
        candidate = current + separator + part if current else part
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(part) > chunk_size:
                # Sub-split oversized part with next separator level
                chunks.extend(_chunk_recursive(part, chunk_size, overlap, remaining_seps))
                current = ""
            else:
                current = part
    if current:
        chunks.append(current)

    # Apply overlap between chunks
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-overlap:] if len(chunks[i - 1]) > overlap else chunks[i - 1]
            overlapped.append(prev_tail + chunks[i])
        chunks = overlapped

    return chunks


def _chunk_character(text, chunk_size, overlap):
    """Fixed-window character splitting."""
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunks.append(text[start:end])
        if end == text_len:
            break
        start += chunk_size - overlap
    return chunks


def _chunk_token(text, chunk_size, overlap, chars_per_token=4):
    """Approximate token-based chunking (configurable chars per token)."""
    char_size = chunk_size * chars_per_token
    char_overlap = overlap * chars_per_token
    return _chunk_character(text, char_size, char_overlap)


def run(ctx):
    dataset_path = ctx.load_input("dataset")
    chunk_size = int(ctx.config.get("chunk_size", 1000))
    overlap = int(ctx.config.get("chunk_overlap", 200))
    strategy = ctx.config.get("strategy", "recursive")
    text_column = ctx.config.get("text_column", "text")
    keep_metadata = ctx.config.get("keep_metadata", True)
    min_chunk_size = int(ctx.config.get("min_chunk_size", 0))
    chars_per_token = int(ctx.config.get("chars_per_token", 4))
    include_chunk_id = ctx.config.get("include_chunk_id", True)

    if overlap >= chunk_size:
        raise ValueError(f"chunk_overlap ({overlap}) must be less than chunk_size ({chunk_size})")

    # Load data — try data.json first, fall back to docs.json for backward compat
    if os.path.isdir(dataset_path):
        data_file = os.path.join(dataset_path, "data.json")
        if not os.path.isfile(data_file):
            alt_file = os.path.join(dataset_path, "docs.json")
            if os.path.isfile(alt_file):
                data_file = alt_file
    else:
        data_file = dataset_path

    if not os.path.isfile(data_file):
        raise FileNotFoundError(f"Dataset not found at: {dataset_path}")

    with open(data_file, "r", encoding="utf-8") as f:
        docs = json.load(f)

    if not isinstance(docs, list):
        raise ValueError("Dataset must be a JSON array")

    ctx.log_message(f"Chunking {len(docs)} documents: strategy={strategy}, size={chunk_size}, overlap={overlap}")

    # Select chunking function
    chunk_fns = {
        "recursive": lambda t: _chunk_recursive(t, chunk_size, overlap),
        "character": lambda t: _chunk_character(t, chunk_size, overlap),
        "token": lambda t: _chunk_token(t, chunk_size, overlap, chars_per_token),
    }
    chunk_fn = chunk_fns.get(strategy)
    if chunk_fn is None:
        ctx.log_message(f"Unknown strategy '{strategy}', defaulting to recursive")
        chunk_fn = chunk_fns["recursive"]

    chunked_data = []
    for idx, doc in enumerate(docs):
        text = str(doc.get(text_column, ""))
        if not text.strip():
            continue

        chunks = chunk_fn(text)

        # Merge tiny chunks with predecessor (RAG retrieval quality)
        if min_chunk_size > 0 and len(chunks) > 1:
            merged_chunks = [chunks[0]]
            for c in chunks[1:]:
                if len(c.strip()) < min_chunk_size:
                    merged_chunks[-1] = merged_chunks[-1] + " " + c
                else:
                    merged_chunks.append(c)
            chunks = merged_chunks

        for c_idx, chunk in enumerate(chunks):
            entry = {text_column: chunk}
            if include_chunk_id:
                entry["doc_id"] = doc.get("id", str(idx))
                entry["chunk_id"] = f"{doc.get('id', str(idx))}_{c_idx}"
                entry["chunk_index"] = c_idx
            if keep_metadata:
                for k, v in doc.items():
                    if k not in (text_column, "id"):
                        entry[k] = v
            chunked_data.append(entry)
        ctx.report_progress(idx + 1, len(docs))

    # Save as data.json (the standard)
    out_path = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "data.json"), "w", encoding="utf-8") as f:
        json.dump(chunked_data, f)

    chunk_sizes = [len(c.get(text_column, "")) for c in chunked_data]
    stats = {
        "total_documents": len(docs),
        "total_chunks": len(chunked_data),
        "avg_chunk_size": round(sum(chunk_sizes) / max(len(chunk_sizes), 1), 1),
        "min_chunk_size": min(chunk_sizes) if chunk_sizes else 0,
        "max_chunk_size": max(chunk_sizes) if chunk_sizes else 0,
    }

    ctx.save_output("dataset", out_path)
    ctx.save_output("stats", stats)
    ctx.log_metric("total_documents", len(docs))
    ctx.log_metric("total_chunks", len(chunked_data))
    ctx.log_message(f"Created {len(chunked_data)} chunks from {len(docs)} documents")
