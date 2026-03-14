"""Document Ingestion — loads PDF, DOCX, TXT, MD, HTML, and RST files from a directory for RAG."""

import glob
import json
import os
import re
import time


def _read_pdf(filepath):
    """Read text from PDF file."""
    try:
        import PyPDF2
        text_parts = []
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            page_count = len(reader.pages)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts), page_count
    except ImportError:
        pass

    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(filepath) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts), page_count
    except ImportError:
        pass

    raise ImportError(
        "PDF reading requires PyPDF2 or pdfplumber. "
        "Install with: pip install PyPDF2  or  pip install pdfplumber"
    )


def _read_docx(filepath):
    """Read text from DOCX file."""
    try:
        import docx
        doc = docx.Document(filepath)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs), len(paragraphs)
    except ImportError:
        raise ImportError(
            "DOCX reading requires python-docx. "
            "Install with: pip install python-docx"
        )


def _read_text(filepath, encoding="utf-8"):
    """Read plain text file."""
    with open(filepath, "r", encoding=encoding, errors="replace") as f:
        content = f.read()
    return content, len(content.splitlines())


def run(ctx):
    folder_path = ctx.config.get("directory_path", "")
    pattern = ctx.config.get("glob_pattern", "*.*")
    recursive = ctx.config.get("recursive", True)
    max_files = int(ctx.config.get("max_files", 0))
    chunk_text = ctx.config.get("chunk_text", False)
    chunk_size = int(ctx.config.get("chunk_size", 1000))
    chunk_overlap = int(ctx.config.get("chunk_overlap", 200))
    language = ctx.config.get("language", "en")
    error_handling = ctx.config.get("error_handling", "skip")
    chunk_strategy = ctx.config.get("chunk_strategy", "character")

    # Apply overrides from connected config input
    try:
        _ci = ctx.load_input("config")
        if _ci:
            _ov = json.load(open(_ci)) if isinstance(_ci, str) and os.path.isfile(_ci) else (_ci if isinstance(_ci, dict) else {})
            if isinstance(_ov, dict) and _ov:
                ctx.log_message(f"Applying {len(_ov)} config override(s) from input")
                folder_path = _ov.get("directory_path", folder_path)
                pattern = _ov.get("glob_pattern", pattern)
                max_files = int(_ov.get("max_files", max_files))
                language = _ov.get("language", language)
                chunk_size = int(_ov.get("chunk_size", chunk_size))
    except (ValueError, KeyError):
        pass

    # Normalize booleans
    if isinstance(recursive, str):
        recursive = recursive.lower() in ("true", "1", "yes")
    if isinstance(chunk_text, str):
        chunk_text = chunk_text.lower() in ("true", "1", "yes")

    ctx.log_message(f"Ingesting documents from '{folder_path}' matching '{pattern}'")
    if recursive:
        ctx.log_message("Recursive search enabled")

    docs = []

    if folder_path:
        folder_path = os.path.expanduser(folder_path)

    if folder_path and os.path.exists(folder_path):

        # Build search path
        if recursive:
            search_path = os.path.join(folder_path, "**", pattern)
        else:
            search_path = os.path.join(folder_path, pattern)

        files = glob.glob(search_path, recursive=recursive)
        # Sort for deterministic output
        files.sort()

        if max_files > 0:
            files = files[:max_files]

        ctx.log_message(f"Found {len(files)} file(s) to ingest")
        ctx.log_metric("simulation_mode", 0.0)

        failed_files = []
        pdf_missing_warned = False
        docx_missing_warned = False

        for i, filepath in enumerate(files):
            ext = os.path.splitext(filepath)[1].lower()
            filename = os.path.basename(filepath)

            try:
                if ext == ".pdf":
                    try:
                        text, page_count = _read_pdf(filepath)
                        doc = {
                            "id": str(i),
                            "filename": filename,
                            "text": text,
                            "format": "pdf",
                            "page_count": page_count,
                        }
                    except ImportError as ie:
                        if not pdf_missing_warned:
                            ctx.log_message(f"WARNING: {ie}")
                            pdf_missing_warned = True
                        ctx.log_message(f"  Skipping PDF: {filename}")
                        continue

                elif ext == ".docx":
                    try:
                        text, para_count = _read_docx(filepath)
                        doc = {
                            "id": str(i),
                            "filename": filename,
                            "text": text,
                            "format": "docx",
                            "paragraph_count": para_count,
                        }
                    except ImportError as ie:
                        if not docx_missing_warned:
                            ctx.log_message(f"WARNING: {ie}")
                            docx_missing_warned = True
                        ctx.log_message(f"  Skipping DOCX: {filename}")
                        continue

                elif ext in (".txt", ".md", ".rst", ".html", ".htm", ".csv", ".log"):
                    text, line_count = _read_text(filepath)
                    doc = {
                        "id": str(i),
                        "filename": filename,
                        "text": text,
                        "format": ext.lstrip("."),
                        "line_count": line_count,
                    }

                else:
                    # Try reading as text, skip binary files
                    try:
                        text, line_count = _read_text(filepath)
                        doc = {
                            "id": str(i),
                            "filename": filename,
                            "text": text,
                            "format": ext.lstrip(".") or "unknown",
                            "line_count": line_count,
                        }
                    except Exception:
                        ctx.log_message(f"  Skipping unsupported format: {filename}")
                        continue

                doc["language"] = language
                doc["char_count"] = len(doc["text"])

                # Optional inline chunking
                if chunk_text and len(doc["text"]) > chunk_size:
                    text = doc["text"]
                    chunks = []

                    if chunk_strategy == "paragraph":
                        # Split on paragraph boundaries (double newline)
                        paragraphs = re.split(r'\n\s*\n', text)
                        current_chunk = ""
                        for para in paragraphs:
                            para = para.strip()
                            if not para:
                                continue
                            if len(current_chunk) + len(para) + 2 > chunk_size and current_chunk:
                                chunks.append({"id": f"{i}_chunk_{len(chunks)}", "filename": filename,
                                    "text": current_chunk.strip(), "format": doc.get("format", ""),
                                    "chunk_index": len(chunks), "language": language,
                                    "char_count": len(current_chunk.strip())})
                                # Keep overlap from end of previous chunk
                                if chunk_overlap > 0:
                                    current_chunk = current_chunk[-chunk_overlap:] + "\n\n" + para
                                else:
                                    current_chunk = para
                            else:
                                current_chunk = (current_chunk + "\n\n" + para) if current_chunk else para
                        if current_chunk.strip():
                            chunks.append({"id": f"{i}_chunk_{len(chunks)}", "filename": filename,
                                "text": current_chunk.strip(), "format": doc.get("format", ""),
                                "chunk_index": len(chunks), "language": language,
                                "char_count": len(current_chunk.strip())})

                    elif chunk_strategy == "sentence":
                        # Split on sentence boundaries
                        sentences = re.split(r'(?<=[.!?])\s+', text)
                        current_chunk = ""
                        for sent in sentences:
                            sent = sent.strip()
                            if not sent:
                                continue
                            if len(current_chunk) + len(sent) + 1 > chunk_size and current_chunk:
                                chunks.append({"id": f"{i}_chunk_{len(chunks)}", "filename": filename,
                                    "text": current_chunk.strip(), "format": doc.get("format", ""),
                                    "chunk_index": len(chunks), "language": language,
                                    "char_count": len(current_chunk.strip())})
                                if chunk_overlap > 0:
                                    current_chunk = current_chunk[-chunk_overlap:] + " " + sent
                                else:
                                    current_chunk = sent
                            else:
                                current_chunk = (current_chunk + " " + sent) if current_chunk else sent
                        if current_chunk.strip():
                            chunks.append({"id": f"{i}_chunk_{len(chunks)}", "filename": filename,
                                "text": current_chunk.strip(), "format": doc.get("format", ""),
                                "chunk_index": len(chunks), "language": language,
                                "char_count": len(current_chunk.strip())})

                    else:
                        # Default character-based sliding window
                        step = max(chunk_size - chunk_overlap, 1)
                        start = 0
                        while start < len(text):
                            chunk = text[start:start + chunk_size]
                            chunks.append({
                                "id": f"{i}_chunk_{len(chunks)}",
                                "filename": filename,
                                "text": chunk,
                                "format": doc.get("format", ""),
                                "chunk_index": len(chunks),
                                "language": language,
                                "char_count": len(chunk),
                            })
                            start += step

                    docs.extend(chunks)
                    ctx.log_message(f"  {filename}: {len(doc['text'])} chars → {len(chunks)} chunks ({chunk_strategy}, overlap={chunk_overlap})")
                else:
                    docs.append(doc)
                    ctx.log_message(f"  {filename}: {len(doc['text'])} chars")

            except Exception as e:
                ctx.log_message(f"  Failed to read {filename}: {e}")
                failed_files.append({"filename": filename, "error": str(e)})
                if error_handling == "fail_fast":
                    raise RuntimeError(f"Document ingestion failed on {filename}: {e}")

            ctx.report_progress(i + 1, max(len(files), 1))

        # Report failed files
        if failed_files:
            ctx.log_message(f"WARNING: {len(failed_files)} file(s) failed to process:")
            for ff in failed_files:
                ctx.log_message(f"  - {ff['filename']}: {ff['error']}")
            ctx.log_metric("files_failed", len(failed_files))

    else:
        ctx.log_message("⚠️ SIMULATION MODE: No directory provided. Results are synthetic demo documents. Provide a valid directory_path for real document ingestion.")
        ctx.log_metric("simulation_mode", 1.0)
        time.sleep(0.5)
        docs = [
            {
                "id": "0",
                "filename": "sample_document_1.txt",
                "text": "This is a sample document describing the benefits of RAG architectures. They help LLMs access external knowledge.",
                "format": "txt",
                "char_count": 112,
                "language": language,
            },
            {
                "id": "1",
                "filename": "sample_document_2.txt",
                "text": "Another document detailing how vector databases like ChromaDB store semantic embeddings for fast retrieval.",
                "format": "txt",
                "char_count": 104,
                "language": language,
            },
        ]
        ctx.report_progress(1, 1)

    out_path = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_path, exist_ok=True)

    with open(os.path.join(out_path, "data.json"), "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2)

    ctx.log_metric("documents_ingested", len(docs))
    ctx.log_metric("total_chars", sum(d.get("char_count", 0) for d in docs))
    ctx.log_message(f"Ingested {len(docs)} document(s)")
    ctx.report_progress(1, 1)
    ctx.save_output("dataset", out_path)

    # Save metrics output
    _total_chars = sum(d.get("char_count", 0) for d in docs)
    _formats = list(set(d.get("format", "") for d in docs))
    _metrics = {"documents_ingested": len(docs), "total_chars": _total_chars, "formats": _formats, "chunked": chunk_text}
    _mp = os.path.join(ctx.run_dir, "metrics.json")
    with open(_mp, "w") as f:
        json.dump(_metrics, f, indent=2)
    ctx.save_output("metrics", _mp)
