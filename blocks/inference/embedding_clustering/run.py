"""Embedding Clustering — cluster embedding vectors using K-Means, DBSCAN, HDBSCAN, or Agglomerative.

Workflows:
  1. Topic discovery: documents -> embed -> cluster -> label topics
  2. Customer segmentation: user descriptions -> embed -> cluster -> segments
  3. Anomaly detection: data -> embed -> cluster -> find outliers (noise points)
  4. Data organization: unstructured corpus -> embed -> cluster -> folders
  5. Deduplication prep: texts -> embed -> cluster -> merge near-duplicates
"""

import json
import os
from collections import Counter


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
            raise ImportError(
                f"NumPy is required to load .npy embeddings file: {path}. "
                f"Install with: pip install numpy"
            )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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

    return [], [], []


def _load_external_labels(ctx):
    """Load labels from the labels input port."""
    if not ctx.inputs.get("labels"):
        return []
    try:
        raw = ctx.load_input("labels")
    except Exception:
        return []
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = _load_json(raw)
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, dict):
                out.append(item.get("label", item.get("text", item.get("name", str(item)))))
            else:
                out.append(str(item))
        return out
    return []


def _auto_eps(X):
    """Estimate a reasonable eps for DBSCAN using k-nearest neighbor distances."""
    try:
        from sklearn.neighbors import NearestNeighbors
        import numpy as np
    except ImportError as e:
        from backend.block_sdk.exceptions import BlockDependencyError
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install scikit-learn numpy",
        )

    k = min(5, len(X) - 1)
    nn = NearestNeighbors(n_neighbors=k)
    nn.fit(X)
    distances, _ = nn.kneighbors(X)
    k_distances = sorted(distances[:, -1])
    eps = float(k_distances[int(len(k_distances) * 0.9)])
    return max(eps, 0.01)


def _compute_quality_metrics(X, cluster_labels):
    """Compute clustering quality metrics."""
    metrics = {}
    unique = set(cluster_labels)
    n_clusters = len(unique - {-1})

    if n_clusters < 2 or n_clusters >= len(X):
        return metrics

    try:
        from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
        import numpy as np

        mask = [c != -1 for c in cluster_labels]
        if sum(mask) >= 2:
            X_clean = np.array([X[i] for i, m in enumerate(mask) if m])
            labels_clean = [c for c, m in zip(cluster_labels, mask) if m]

            if len(set(labels_clean)) >= 2:
                metrics["silhouette_score"] = round(float(silhouette_score(X_clean, labels_clean)), 4)
                metrics["calinski_harabasz_score"] = round(float(calinski_harabasz_score(X_clean, labels_clean)), 2)
                metrics["davies_bouldin_score"] = round(float(davies_bouldin_score(X_clean, labels_clean)), 4)
    except ImportError as e:
        from backend.block_sdk.exceptions import BlockDependencyError
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install numpy scikit-learn",
        )

    return metrics


def run(ctx):
    method = ctx.config.get("method", "kmeans")
    n_clusters = int(ctx.config.get("n_clusters", 8))
    min_cluster_size = int(ctx.config.get("min_cluster_size", 5))
    eps = float(ctx.config.get("eps", 0.0))
    linkage = ctx.config.get("linkage", "ward")
    random_seed = int(ctx.config.get("random_seed", 42))
    embedding_column = ctx.config.get("embedding_column", "_embedding")
    normalize = ctx.config.get("normalize", False)
    include_centroids = ctx.config.get("include_centroids", False)
    n_init = int(ctx.config.get("n_init", 10))
    dataset_format = ctx.config.get("dataset_format", "json")

    # ── Load embeddings from either embeddings or dataset input ──
    vectors = []
    embedded_labels = []
    metadata_rows = []

    # Try dataset input first (from embedding_generator output)
    if ctx.inputs.get("dataset"):
        try:
            ds_path = ctx.load_input("dataset")
            data_file = os.path.join(ds_path, "data.json") if os.path.isdir(ds_path) else ds_path
            with open(data_file, "r", encoding="utf-8") as f:
                rows = json.load(f)
            vectors, embedded_labels, metadata_rows = _extract_vectors_and_labels(rows, embedding_column)
            if vectors:
                ctx.log_message(f"Loaded {len(vectors)} embeddings from dataset (column='{embedding_column}')")
        except Exception as e:
            ctx.log_message(f"Dataset load error: {e}")

    # Fall back to embeddings input
    if not vectors and ctx.inputs.get("embeddings"):
        raw_emb = ctx.load_input("embeddings")
        if isinstance(raw_emb, str):
            raw_emb = _load_json(raw_emb)
        vectors, embedded_labels, metadata_rows = _extract_vectors_and_labels(raw_emb, embedding_column)
        if vectors:
            ctx.log_message(f"Loaded {len(vectors)} embeddings from embeddings input")

    if not vectors or len(vectors) < 2:
        raise ValueError("Need at least 2 embeddings to cluster. Connect 'dataset' or 'embeddings' input.")

    # Filter out empty vectors
    valid_indices = [i for i, v in enumerate(vectors) if v and len(v) > 0]
    if len(valid_indices) < len(vectors):
        ctx.log_message(f"Filtered {len(vectors) - len(valid_indices)} empty embeddings")
        vectors = [vectors[i] for i in valid_indices]
        embedded_labels = [embedded_labels[i] for i in valid_indices] if embedded_labels else list(range(len(vectors)))
        metadata_rows = [metadata_rows[i] for i in valid_indices] if metadata_rows else []

    dim = len(vectors[0])
    ctx.log_message(f"Clustering {len(vectors)} embeddings (dim={dim}) with {method}")

    # ── Load external labels (override embedded labels if provided) ──
    external_labels = _load_external_labels(ctx)
    if external_labels:
        if len(external_labels) >= len(vectors):
            original_labels = external_labels[:len(vectors)]
        else:
            original_labels = external_labels + [str(i) for i in range(len(external_labels), len(vectors))]
        ctx.log_message(f"Using {len(external_labels)} external labels")
    else:
        original_labels = [str(lbl) for lbl in embedded_labels]

    ctx.report_progress(1, 4)

    # ── Cluster ──────────────────────────────────────────────────
    try:
        import numpy as np
        X = np.array(vectors, dtype=np.float64)

        if normalize:
            norms = np.linalg.norm(X, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            X = X / norms
            ctx.log_message("Embeddings L2-normalized")

        if method == "kmeans":
            from sklearn.cluster import KMeans
            k = min(n_clusters, len(vectors))
            model = KMeans(n_clusters=k, n_init=n_init, random_state=random_seed)
            cluster_labels = model.fit_predict(X).tolist()
            ctx.log_message(f"K-Means: {k} clusters")

        elif method == "dbscan":
            from sklearn.cluster import DBSCAN
            actual_eps = eps if eps > 0 else _auto_eps(X)
            if eps <= 0:
                ctx.log_message(f"Auto-estimated eps={actual_eps:.4f}")
            model = DBSCAN(eps=actual_eps, min_samples=min_cluster_size)
            cluster_labels = model.fit_predict(X).tolist()
            n_found = len(set(cluster_labels) - {-1})
            ctx.log_message(f"DBSCAN: {n_found} clusters (eps={actual_eps:.4f})")

        elif method == "hdbscan":
            try:
                import hdbscan
                model = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size)
                cluster_labels = model.fit_predict(X).tolist()
            except ImportError:
                ctx.log_message("hdbscan not installed — falling back to DBSCAN")
                actual_eps = eps if eps > 0 else _auto_eps(X)
                from sklearn.cluster import DBSCAN
                model = DBSCAN(eps=actual_eps, min_samples=min_cluster_size)
                cluster_labels = model.fit_predict(X).tolist()
            n_found = len(set(cluster_labels) - {-1})
            ctx.log_message(f"Clusters found: {n_found}")

        elif method == "agglomerative":
            from sklearn.cluster import AgglomerativeClustering
            k = min(n_clusters, len(vectors))
            model = AgglomerativeClustering(n_clusters=k, linkage=linkage)
            cluster_labels = model.fit_predict(X).tolist()
            ctx.log_message(f"Agglomerative: {k} clusters (linkage={linkage})")

        else:
            raise ValueError(f"Unknown clustering method: {method}")

    except ImportError as e:
        from backend.block_sdk.exceptions import BlockDependencyError
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install numpy scikit-learn",
        )

    ctx.report_progress(2, 4)

    # ── Build clustered dataset output ───────────────────────────
    clustered = []
    for i, (label, cluster_id) in enumerate(zip(original_labels, cluster_labels)):
        entry = {"index": i, "label": str(label), "cluster": int(cluster_id)}
        # Include original metadata fields if available
        if i < len(metadata_rows) and isinstance(metadata_rows[i], dict):
            for key, val in metadata_rows[i].items():
                if key not in entry and key != embedding_column:
                    entry[key] = val
        clustered.append(entry)

    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    if dataset_format == "jsonl":
        out_path = os.path.join(out_dir, "data.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for row in clustered:
                f.write(json.dumps(row) + "\n")
    elif dataset_format == "csv":
        import csv
        out_path = os.path.join(out_dir, "data.csv")
        if clustered:
            keys = list(clustered[0].keys())
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(clustered)
        else:
            with open(out_path, "w") as f:
                f.write("")
    else:
        out_path = os.path.join(out_dir, "data.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(clustered, f, indent=2)
    ctx.save_output("dataset", out_dir)

    ctx.report_progress(3, 4)

    # ── Build labeled embeddings output ──────────────────────────
    labeled_embeddings = {
        "embeddings": vectors,
        "labels": [str(label) for label in original_labels],
        "clusters": cluster_labels,
    }
    emb_path = os.path.join(ctx.run_dir, "labeled_embeddings.json")
    with open(emb_path, "w", encoding="utf-8") as f:
        json.dump(labeled_embeddings, f)
    ctx.save_output("embeddings", emb_path)

    # ── Compute stats and quality metrics ────────────────────────
    cluster_counts = Counter(cluster_labels)
    num_clusters = len(set(cluster_labels) - {-1})
    noise_count = cluster_labels.count(-1) if -1 in cluster_labels else 0

    stats = {
        "total_points": len(vectors),
        "embedding_dimension": dim,
        "method": method,
        "num_clusters": num_clusters,
        "noise_points": noise_count,
        "cluster_sizes": {str(k): v for k, v in sorted(cluster_counts.items())},
    }

    try:
        import numpy as np
        quality = _compute_quality_metrics(np.array(vectors), cluster_labels)
        stats.update(quality)

        if include_centroids:
            X_arr = np.array(vectors, dtype=np.float64)
            centroids = {}
            for cid in sorted(set(cluster_labels)):
                if cid == -1:
                    continue
                mask = [i for i, c in enumerate(cluster_labels) if c == cid]
                centroid = X_arr[mask].mean(axis=0).tolist()
                centroids[str(cid)] = [round(v, 6) for v in centroid]
            stats["centroids"] = centroids
            ctx.log_message(f"Computed {len(centroids)} cluster centroids")
    except Exception:
        pass

    ctx.save_output("metrics", stats)

    ctx.log_metric("num_clusters", num_clusters)
    ctx.log_metric("noise_points", noise_count)
    if "silhouette_score" in stats:
        ctx.log_metric("silhouette_score", stats["silhouette_score"])

    ctx.log_message(
        f"Done — {num_clusters} clusters, {noise_count} noise points"
        + (f", silhouette={stats['silhouette_score']}" if "silhouette_score" in stats else "")
    )
    ctx.report_progress(4, 4)
