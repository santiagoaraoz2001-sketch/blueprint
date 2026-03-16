"""Embedding Visualizer — reduce high-dimensional embeddings to 2D/3D for scatter-plot visualization."""

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
            raise BlockDependencyError(
                "numpy",
                f"NumPy is required to load .npy embeddings file: {path}.",
                install_hint="pip install numpy"
            )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_vectors_labels_clusters(raw, embedding_column="_embedding"):
    """Parse flexible embedding formats into (vectors, labels, clusters, metadata_rows)."""
    vectors, labels, clusters, metadata = [], [], [], []

    if raw is None:
        return vectors, labels, clusters, metadata

    if isinstance(raw, dict):
        vectors = raw.get("embeddings", raw.get("vectors", []))
        labels = raw.get("labels", raw.get("ids", list(range(len(vectors)))))
        clusters = raw.get("clusters", [])
        return vectors, labels, clusters, metadata

    if isinstance(raw, list):
        if not raw:
            return vectors, labels, clusters, metadata
        if isinstance(raw[0], dict):
            for i, item in enumerate(raw):
                emb = item.get(embedding_column, item.get("embedding", item.get("vector", item.get("_embedding", []))))
                vectors.append(emb)
                labels.append(item.get("label", item.get("id", item.get("text", i))))
                clusters.append(item.get("cluster", -1))
                metadata.append(item)
            return vectors, labels, clusters, metadata
        if isinstance(raw[0], (list, tuple)):
            return raw, list(range(len(raw))), [], metadata

    return vectors, labels, clusters, metadata


def _load_external_labels(ctx):
    """Load labels/clusters from the labels input port."""
    if not ctx.inputs.get("labels"):
        return [], []
    try:
        raw = ctx.load_input("labels")
    except (ValueError, KeyError):
        return [], []
    if raw is None:
        return [], []
    if isinstance(raw, str):
        raw = _load_json(raw)

    ext_labels = []
    ext_clusters = []

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                ext_labels.append(str(item.get("label", item.get("text", item.get("name", "")))))
                ext_clusters.append(item.get("cluster", -1))
            elif isinstance(item, (str, int, float)):
                ext_labels.append(str(item))
        return ext_labels, ext_clusters

    if isinstance(raw, dict):
        # Could be {"labels": [...], "clusters": [...]}
        ext_labels = [str(l) for l in raw.get("labels", [])]
        ext_clusters = raw.get("clusters", [])
        # Or rows format
        for key in ("rows", "data"):
            if key in raw and isinstance(raw[key], list):
                return _load_external_labels_from_list(raw[key])
        return ext_labels, ext_clusters

    return ext_labels, ext_clusters


def _load_external_labels_from_list(items):
    """Helper to extract labels and clusters from a list of dicts."""
    labels = []
    clusters = []
    for item in items:
        if isinstance(item, dict):
            labels.append(str(item.get("label", item.get("text", ""))))
            clusters.append(item.get("cluster", -1))
        else:
            labels.append(str(item))
    return labels, clusters


def run(ctx):
    method = ctx.config.get("method", "pca")
    dimensions = int(ctx.config.get("dimensions", 2))
    perplexity = int(ctx.config.get("perplexity", 30))
    learning_rate_cfg = float(ctx.config.get("learning_rate", 0.0))
    n_neighbors = int(ctx.config.get("n_neighbors", 15))
    min_dist = float(ctx.config.get("min_dist", 0.1))
    embedding_column = ctx.config.get("embedding_column", "_embedding")
    normalize = ctx.config.get("normalize", False)
    include_metadata = ctx.config.get("include_metadata", False)

    # ── Load embeddings (from dataset or embeddings input) ────────
    vectors = []
    embedded_labels = []
    embedded_clusters = []
    source_metadata = []

    # Try dataset input first (from embedding_generator output)
    if ctx.inputs.get("dataset"):
        try:
            ds_path = ctx.load_input("dataset")
            data_file = os.path.join(ds_path, "data.json") if os.path.isdir(ds_path) else ds_path
            with open(data_file, "r", encoding="utf-8") as f:
                rows = json.load(f)
            vectors, embedded_labels, embedded_clusters, source_metadata = _extract_vectors_labels_clusters(rows, embedding_column)
            if vectors:
                ctx.log_message(f"Loaded {len(vectors)} embeddings from dataset (column='{embedding_column}')")
        except Exception as e:
            ctx.log_message(f"Dataset load error: {e}")

    # Fall back to embeddings input
    if not vectors and ctx.inputs.get("embeddings"):
        raw_emb = ctx.load_input("embeddings")
        if isinstance(raw_emb, str):
            raw_emb = _load_json(raw_emb)
        vectors, embedded_labels, embedded_clusters, source_metadata = _extract_vectors_labels_clusters(raw_emb, embedding_column)

    if not vectors:
        raise BlockInputError("No embedding vectors received. Connect 'dataset' or 'embeddings' input.", recoverable=False)

    dim = len(vectors[0])
    ctx.log_message(f"Loaded {len(vectors)} embeddings (dim={dim})")

    # ── Load external labels (override embedded if provided) ─────
    ext_labels, ext_clusters = _load_external_labels(ctx)

    if ext_labels and len(ext_labels) >= len(vectors):
        labels = ext_labels[:len(vectors)]
        ctx.log_message(f"Using {len(labels)} external labels")
    else:
        labels = [str(l) for l in embedded_labels]

    if ext_clusters and len(ext_clusters) >= len(vectors):
        clusters = ext_clusters[:len(vectors)]
    elif embedded_clusters and len(embedded_clusters) >= len(vectors):
        clusters = embedded_clusters[:len(vectors)]
    else:
        clusters = []

    ctx.report_progress(1, 4)

    # ── Dimensionality reduction ─────────────────────────────────
    try:
        import numpy as np
        X = np.array(vectors, dtype=np.float64)

        if normalize:
            norms = np.linalg.norm(X, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            X = X / norms
            ctx.log_message("Embeddings L2-normalized")

        if method == "pca":
            from sklearn.decomposition import PCA
            n_components = min(dimensions, dim, len(vectors))
            pca = PCA(n_components=n_components, random_state=42)
            coords = pca.fit_transform(X)
            variance = sum(pca.explained_variance_ratio_)
            ctx.log_message(f"PCA: {n_components}D, explained variance = {variance:.2%}")

        elif method == "tsne":
            from sklearn.manifold import TSNE
            perp = min(perplexity, max(2, len(vectors) - 1))
            tsne_kwargs = {
                "n_components": dimensions,
                "perplexity": perp,
                "random_state": 42,
            }
            if learning_rate_cfg > 0:
                tsne_kwargs["learning_rate"] = learning_rate_cfg
            else:
                tsne_kwargs["learning_rate"] = "auto"
            tsne = TSNE(**tsne_kwargs)
            coords = tsne.fit_transform(X)
            ctx.log_message(f"t-SNE: perplexity={perp}, lr={tsne_kwargs['learning_rate']}")

        elif method == "umap":
            try:
                import umap
                reducer = umap.UMAP(
                    n_components=dimensions,
                    n_neighbors=min(n_neighbors, len(vectors) - 1),
                    min_dist=min_dist,
                    random_state=42,
                )
                coords = reducer.fit_transform(X)
                ctx.log_message(f"UMAP: n_neighbors={n_neighbors}, min_dist={min_dist}")
            except ImportError:
                ctx.log_message("umap-learn not installed — falling back to PCA")
                from sklearn.decomposition import PCA
                pca = PCA(n_components=dimensions, random_state=42)
                coords = pca.fit_transform(X)
                method = "pca_fallback"

        else:
            raise BlockConfigError("method", f"Unknown method: {method}")

        reduced = coords.tolist()

    except ImportError as e:
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install numpy scikit-learn",
        )

    ctx.report_progress(2, 4)

    # ── Build visualization artifact ─────────────────────────────
    viz_data = {
        "method": method,
        "dimensions": dimensions,
        "num_points": len(reduced),
        "original_dimension": dim,
        "points": [],
    }

    for i, coord in enumerate(reduced):
        point = {
            "index": i,
            "label": labels[i] if i < len(labels) else str(i),
        }
        if clusters and i < len(clusters):
            point["cluster"] = int(clusters[i])
        if dimensions >= 2:
            point["x"] = round(coord[0], 6)
            point["y"] = round(coord[1], 6)
        if dimensions >= 3 and len(coord) >= 3:
            point["z"] = round(coord[2], 6)
        viz_data["points"].append(point)

    viz_path = os.path.join(ctx.run_dir, "visualization.json")
    with open(viz_path, "w", encoding="utf-8") as f:
        json.dump(viz_data, f, indent=2)
    ctx.save_output("artifact", viz_path)

    ctx.report_progress(3, 4)

    # ── Build coordinates dataset output ─────────────────────────
    coords_dataset = []
    for i, coord in enumerate(reduced):
        row = {
            "index": i,
            "label": labels[i] if i < len(labels) else str(i),
            "x": round(coord[0], 6),
            "y": round(coord[1], 6) if len(coord) > 1 else 0.0,
        }
        if dimensions >= 3 and len(coord) >= 3:
            row["z"] = round(coord[2], 6)
        if clusters and i < len(clusters):
            row["cluster"] = int(clusters[i])
        # Carry through source metadata fields (for interactive chart tooltips)
        if include_metadata and i < len(source_metadata) and isinstance(source_metadata[i], dict):
            for key, val in source_metadata[i].items():
                if key not in row and key != embedding_column and not isinstance(val, (list, dict)):
                    row[key] = val
        coords_dataset.append(row)

    coords_path = os.path.join(ctx.run_dir, "coordinates.json")
    with open(coords_path, "w", encoding="utf-8") as f:
        json.dump(coords_dataset, f, indent=2)
    ctx.save_output("viz_dataset", coords_path)

    ctx.log_metric("point_count", len(reduced))
    ctx.log_metric("dimensions", dim)
    unique_clusters = len(set(c for c in clusters if c != -1)) if clusters else 0
    ctx.log_metric("clusters_found", unique_clusters)

    ctx.log_message(f"Visualization: {len(reduced)} points in {dimensions}D ({method})")
    ctx.report_progress(4, 4)
