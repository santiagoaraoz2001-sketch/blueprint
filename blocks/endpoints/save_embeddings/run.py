"""Save Embeddings — save vector embeddings to file."""

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


def _extract_vectors(data):
    """Extract numeric vectors from various data formats."""
    # If it's already a numpy array path or FAISS index path, return as-is
    if isinstance(data, str) and os.path.isfile(data):
        return {"type": "file", "path": data}

    # Try to get vectors from dict
    if isinstance(data, dict):
        for key in ["embeddings", "vectors", "data", "embedding"]:
            if key in data:
                vecs = data[key]
                if isinstance(vecs, list):
                    return {"type": "list", "vectors": vecs, "metadata": data}
                return {"type": "unknown", "data": data}
        return {"type": "dict", "data": data}

    # List of vectors
    if isinstance(data, list):
        if len(data) > 0:
            first = data[0]
            if isinstance(first, list) and all(isinstance(x, (int, float)) for x in first):
                return {"type": "list", "vectors": data}
            if isinstance(first, dict):
                # List of dicts with embedding field
                vecs = []
                for item in data:
                    for key in ["embedding", "vector", "embeddings"]:
                        if key in item:
                            vecs.append(item[key])
                            break
                if vecs:
                    return {"type": "list", "vectors": vecs, "metadata": data}
        return {"type": "list", "vectors": data}

    return {"type": "unknown", "data": data}


def run(ctx):
    output_path = ctx.config.get("output_path", "./output").strip()
    filename = ctx.config.get("filename", "embeddings").strip()
    fmt = ctx.config.get("format", "npy").lower().strip()
    save_metadata = ctx.config.get("save_metadata", True)
    overwrite = ctx.config.get("overwrite_existing", True)
    normalize = ctx.config.get("normalize", False)
    precision = ctx.config.get("precision", "float32").lower().strip()

    ctx.log_message(f"Save Embeddings starting (format={fmt})")
    ctx.report_progress(0, 4)

    # ── Loop-aware file handling ──
    loop = ctx.get_loop_metadata()
    if isinstance(loop, dict):
        file_mode = loop.get("file_mode", "overwrite")
        iteration = loop.get("iteration", 0)
        ctx.log_message(f"[Loop iter {iteration}] file_mode={file_mode}")
        if file_mode == "append":
            ctx.log_message("WARNING: Embeddings format does not support append mode, using overwrite")
            file_mode = "overwrite"
    else:
        file_mode = "overwrite"
        iteration = 0

    # Loop versioned: create iteration-specific filename
    if file_mode == "versioned":
        filename = f"{filename}_iter{iteration}"

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 4)
    # Use load_input directly — embeddings may be binary file paths (.npy, .faiss)
    # that resolve_as_data cannot handle (it tries to read them as text/JSON).
    raw_data = ctx.load_input("embeddings")
    if raw_data is None:
        raise BlockInputError(
            "No embedding data provided. Connect an 'embeddings' input.",
            recoverable=False,
        )

    vec_info = _extract_vectors(raw_data)
    ctx.log_message(f"Embedding data type: {vec_info['type']}")

    # ---- Step 2: Resolve output path ----
    ctx.report_progress(2, 4)
    if os.path.isabs(output_path):
        out_dir = output_path
    else:
        out_dir = os.path.join(ctx.run_dir, output_path)
    os.makedirs(out_dir, exist_ok=True)

    # ---- Step 3: Save embeddings ----
    ctx.report_progress(3, 4)
    num_vectors = 0
    dimensions = 0

    if vec_info["type"] == "file":
        # Copy existing file
        import shutil
        src = vec_info["path"]
        ext = os.path.splitext(src)[1]
        out_filepath = os.path.join(out_dir, filename + ext)
        if os.path.exists(out_filepath) and not overwrite:
            raise BlockInputError(
                f"File already exists: {out_filepath}",
                recoverable=True,
            )
        shutil.copy2(src, out_filepath)
        ctx.log_message(f"Copied embedding file from {src}")
        file_size = os.path.getsize(out_filepath)
        # Extract metadata from numpy files for accurate reporting
        if ext.lower() == ".npy":
            try:
                import numpy as np
                arr = np.load(src)
                num_vectors = arr.shape[0]
                dimensions = arr.shape[1] if arr.ndim > 1 else 0
            except Exception:
                pass

    elif vec_info["type"] == "list" and "vectors" in vec_info:
        vectors = vec_info["vectors"]
        num_vectors = len(vectors)
        if num_vectors > 0 and isinstance(vectors[0], list):
            dimensions = len(vectors[0])

        ctx.log_message(f"Processing {num_vectors} vectors (dim={dimensions})")

        if fmt in ("npy", "npz"):
            try:
                import numpy as np
                dtype_map = {"float16": np.float16, "float32": np.float32, "float64": np.float64}
                np_dtype = dtype_map.get(precision, np.float32)
                arr = np.array(vectors, dtype=np_dtype)
                num_vectors = arr.shape[0]
                dimensions = arr.shape[1] if arr.ndim > 1 else 0
                # L2 normalize if requested
                if normalize and arr.ndim > 1:
                    norms = np.linalg.norm(arr, axis=1, keepdims=True)
                    norms[norms == 0] = 1
                    arr = arr / norms
                    ctx.log_message("Applied L2 normalization")
            except ImportError as e:
                missing = getattr(e, "name", None) or "numpy"
                raise BlockDependencyError(
                    missing,
                    f"Required library not installed: {e}",
                    install_hint="pip install numpy",
                )
            except (ValueError, TypeError) as e:
                raise BlockInputError(
                    f"Cannot convert embedding data to numeric array: {e}",
                    details=f"Got {num_vectors} items, first item type: {type(vectors[0]).__name__ if vectors else 'N/A'}",
                    recoverable=False,
                )

            if fmt == "npy":
                out_filepath = os.path.join(out_dir, filename + ".npy")
                if os.path.exists(out_filepath) and not overwrite:
                    raise BlockInputError(f"File already exists: {out_filepath}", recoverable=True)
                np.save(out_filepath, arr)
            else:
                out_filepath = os.path.join(out_dir, filename + ".npz")
                if os.path.exists(out_filepath) and not overwrite:
                    raise BlockInputError(f"File already exists: {out_filepath}", recoverable=True)
                np.savez_compressed(out_filepath, embeddings=arr)

        elif fmt == "faiss":
            try:
                import numpy as np
                import faiss
                arr = np.array(vectors, dtype=np.float32)  # FAISS requires float32
                num_vectors = arr.shape[0]
                dimensions = arr.shape[1] if arr.ndim > 1 else 0
                if dimensions == 0:
                    raise BlockInputError(
                        "Cannot create FAISS index: vectors must be 2D (each vector needs a dimension > 0)",
                        details=f"Array shape: {arr.shape}",
                        recoverable=False,
                    )
                # L2 normalize if requested
                if normalize and arr.ndim > 1:
                    norms = np.linalg.norm(arr, axis=1, keepdims=True)
                    norms[norms == 0] = 1
                    arr = arr / norms
                    ctx.log_message("Applied L2 normalization")
                index = faiss.IndexFlatL2(dimensions)
                index.add(arr)
                out_filepath = os.path.join(out_dir, filename + ".faiss")
                if os.path.exists(out_filepath) and not overwrite:
                    raise BlockInputError(f"File already exists: {out_filepath}", recoverable=True)
                faiss.write_index(index, out_filepath)
            except ImportError as e:
                missing = getattr(e, "name", None) or "faiss"
                raise BlockDependencyError(
                    missing,
                    f"Required library not installed: {e}",
                    install_hint="pip install faiss-cpu numpy",
                )

        elif fmt == "json":
            out_filepath = os.path.join(out_dir, filename + ".json")
            if os.path.exists(out_filepath) and not overwrite:
                raise BlockInputError(f"File already exists: {out_filepath}", recoverable=True)
            with open(out_filepath, "w", encoding="utf-8") as f:
                json.dump({"embeddings": vectors, "count": num_vectors, "dimensions": dimensions}, f)
        else:
            raise BlockInputError(
                f"Cannot save embeddings in {fmt} format: unsupported format",
                details="Supported formats: npy, npz, faiss, json",
                recoverable=True,
            )

        file_size = os.path.getsize(out_filepath)

    else:
        # Fallback: save as JSON
        out_filepath = os.path.join(out_dir, filename + ".json")
        if os.path.exists(out_filepath) and not overwrite:
            raise BlockInputError(f"File already exists: {out_filepath}", recoverable=True)
        with open(out_filepath, "w", encoding="utf-8") as f:
            json.dump(vec_info.get("data", raw_data), f, indent=2, default=str)
        file_size = os.path.getsize(out_filepath)
        ctx.log_message("Saved embedding data as JSON (could not extract vector array)")

    # Save metadata sidecar
    if save_metadata:
        meta = {
            "format": fmt,
            "num_vectors": num_vectors,
            "dimensions": dimensions,
            "file_size_bytes": file_size,
        }
        meta_path = os.path.join(out_dir, filename + ".meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    # ---- Step 4: Finalize ----
    ctx.report_progress(4, 4)
    ctx.log_message(f"Saved {num_vectors} vectors (dim={dimensions}) to {out_filepath} ({file_size:,} bytes)")

    ctx.save_output("file_path", out_filepath)
    ctx.save_output("summary", {
        "num_vectors": num_vectors,
        "dimensions": dimensions,
        "file_size_bytes": file_size,
        "format": fmt,
    })
    ctx.save_artifact("embeddings_output", out_filepath)
    ctx.log_metric("num_vectors", float(num_vectors))
    ctx.log_metric("dimensions", float(dimensions))
    ctx.log_metric("file_size_bytes", float(file_size))

    ctx.log_message("Save Embeddings complete.")
