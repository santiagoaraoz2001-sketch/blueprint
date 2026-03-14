"""Save Embeddings — save vector embeddings to file."""

import json
import os


def _resolve_data(raw):
    """Resolve raw input to embedding data."""
    if isinstance(raw, str):
        if os.path.isfile(raw):
            # Could be a .npy, .json, or directory
            ext = os.path.splitext(raw)[1].lower()
            if ext == ".json":
                with open(raw, "r", encoding="utf-8") as f:
                    return json.load(f)
            return raw  # Return path for binary files
        if os.path.isdir(raw):
            # Check for known embedding files
            for name in ["embeddings.npy", "embeddings.json", "index.faiss", "data.json"]:
                fpath = os.path.join(raw, name)
                if os.path.isfile(fpath):
                    return fpath
            return raw
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw
    return raw


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

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 4)
    raw_data = ctx.load_input("embeddings")
    if raw_data is None:
        raise ValueError("No embedding data provided. Connect an 'embeddings' input.")

    data = _resolve_data(raw_data)
    vec_info = _extract_vectors(data)
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
            raise FileExistsError(f"File exists: {out_filepath}")
        shutil.copy2(src, out_filepath)
        ctx.log_message(f"Copied embedding file from {src}")
        file_size = os.path.getsize(out_filepath)

    elif vec_info["type"] == "list" and "vectors" in vec_info:
        vectors = vec_info["vectors"]
        num_vectors = len(vectors)
        if num_vectors > 0 and isinstance(vectors[0], list):
            dimensions = len(vectors[0])

        ctx.log_message(f"Processing {num_vectors} vectors (dim={dimensions})")

        if fmt == "npy" or fmt == "npz":
            try:
                import numpy as np
                np_dtype = np.float16 if precision == "float16" else np.float32
                arr = np.array(vectors, dtype=np_dtype)
                num_vectors = arr.shape[0]
                dimensions = arr.shape[1] if arr.ndim > 1 else 0
                # L2 normalize if requested
                if normalize and arr.ndim > 1:
                    norms = np.linalg.norm(arr, axis=1, keepdims=True)
                    norms[norms == 0] = 1
                    arr = arr / norms
                    ctx.log_message("Applied L2 normalization")
            except ImportError:
                raise ImportError("NumPy is required for npy/npz format. Install with: pip install numpy")

            if fmt == "npy":
                out_filepath = os.path.join(out_dir, filename + ".npy")
                if os.path.exists(out_filepath) and not overwrite:
                    raise FileExistsError(f"File exists: {out_filepath}")
                np.save(out_filepath, arr)
            else:
                out_filepath = os.path.join(out_dir, filename + ".npz")
                if os.path.exists(out_filepath) and not overwrite:
                    raise FileExistsError(f"File exists: {out_filepath}")
                np.savez_compressed(out_filepath, embeddings=arr)

        elif fmt == "faiss":
            try:
                import numpy as np
                import faiss
                arr = np.array(vectors, dtype=np.float32)  # FAISS requires float32
                num_vectors = arr.shape[0]
                dimensions = arr.shape[1] if arr.ndim > 1 else 0
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
                    raise FileExistsError(f"File exists: {out_filepath}")
                faiss.write_index(index, out_filepath)
            except ImportError:
                raise ImportError("faiss-cpu is required for FAISS format. Install with: pip install faiss-cpu")

        elif fmt == "json":
            out_filepath = os.path.join(out_dir, filename + ".json")
            if os.path.exists(out_filepath) and not overwrite:
                raise FileExistsError(f"File exists: {out_filepath}")
            with open(out_filepath, "w", encoding="utf-8") as f:
                json.dump({"embeddings": vectors, "count": num_vectors, "dimensions": dimensions}, f)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

        file_size = os.path.getsize(out_filepath)

    else:
        # Fallback: save as JSON
        out_filepath = os.path.join(out_dir, filename + ".json")
        if os.path.exists(out_filepath) and not overwrite:
            raise FileExistsError(f"File exists: {out_filepath}")
        with open(out_filepath, "w", encoding="utf-8") as f:
            json.dump(vec_info.get("data", data), f, indent=2, default=str)
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
