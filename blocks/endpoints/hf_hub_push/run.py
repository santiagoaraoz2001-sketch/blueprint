"""HuggingFace Hub Push — upload model or dataset to HuggingFace Hub."""

import json
import os
import posixpath

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


def _resolve_upload_info(data):
    """Determine upload type from resolved data."""
    if isinstance(data, dict):
        for key in ["model_path", "path", "output_path", "file_path"]:
            if key in data and isinstance(data[key], str) and os.path.exists(data[key]):
                path = data[key]
                return {"type": "directory" if os.path.isdir(path) else "file", "path": path, "metadata": data}
        return {"type": "data", "data": data}
    if isinstance(data, list):
        return {"type": "data", "data": data}
    return {"type": "data", "data": data}


def run(ctx):
    repo_id = ctx.config.get("repo_id", "").strip()
    repo_type = ctx.config.get("repo_type", "model").lower().strip()
    private = ctx.config.get("private", True)
    commit_message = ctx.config.get("commit_message", "Upload from Blueprint").strip()
    hf_token = ctx.config.get("hf_token", "").strip()
    create_repo = ctx.config.get("create_repo", True)
    revision = ctx.config.get("revision", "main").strip()
    path_in_repo = ctx.config.get("path_in_repo", "").strip()

    if not repo_id:
        raise BlockInputError(
            "Repository ID is required (e.g. 'username/model-name').",
            recoverable=True,
        )

    if not hf_token:
        hf_token = os.environ.get("HF_TOKEN", "") or os.environ.get("HUGGING_FACE_HUB_TOKEN", "")
    if not hf_token:
        raise BlockInputError(
            "HuggingFace token is required. Set it in the config, "
            "use $secret:HF_TOKEN, or set the HF_TOKEN environment variable.",
            recoverable=True,
        )

    ctx.log_message(f"HF Hub Push starting (repo={repo_id}, type={repo_type})")
    ctx.report_progress(0, 4)

    # ---- Step 1: Import huggingface_hub ----
    ctx.report_progress(1, 4)
    try:
        from huggingface_hub import HfApi
    except ImportError as e:
        missing = getattr(e, "name", None) or "huggingface_hub"
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install huggingface_hub",
        )

    api = HfApi(token=hf_token)

    # ---- Step 2: Load and resolve data ----
    ctx.report_progress(2, 4)
    # Use load_input directly — hf_hub_push needs to detect directory/file paths
    # from upstream dicts, and resolve_as_data would wrap dicts in [dict],
    # hiding path references that _resolve_upload_info needs to inspect.
    raw_data = ctx.load_input("data")
    if raw_data is None:
        raise BlockInputError(
            "No input data provided. Connect a 'data' input.",
            recoverable=False,
        )

    # If upstream sent a directory path string, resolve it directly
    if isinstance(raw_data, str) and os.path.isdir(raw_data):
        resolved = {"type": "directory", "path": raw_data}
    elif isinstance(raw_data, str) and os.path.isfile(raw_data):
        resolved = {"type": "file", "path": raw_data}
    else:
        resolved = _resolve_upload_info(raw_data)
    ctx.log_message(f"Upload source type: {resolved['type']}")

    # ---- Step 3: Create repo if needed ----
    if create_repo:
        try:
            api.create_repo(
                repo_id=repo_id,
                repo_type=repo_type,
                private=private,
                exist_ok=True,
            )
            ctx.log_message(f"Repository ensured: {repo_id}")
        except Exception as e:
            ctx.log_message(f"WARNING: Could not create/verify repo: {e}")

    # ---- Step 4: Upload ----
    ctx.report_progress(3, 4)
    uploaded_files = 0
    repo_url = f"https://huggingface.co/{repo_id}"

    if resolved["type"] == "directory":
        path = resolved["path"]
        upload_kwargs = dict(
            folder_path=path,
            repo_id=repo_id,
            repo_type=repo_type,
            commit_message=commit_message,
            revision=revision,
        )
        if path_in_repo:
            upload_kwargs["path_in_repo"] = path_in_repo
        api.upload_folder(**upload_kwargs)
        uploaded_files = sum(1 for _, _, files in os.walk(path) for _ in files)
        ctx.log_message(f"Uploaded directory: {path} ({uploaded_files} files)")

    elif resolved["type"] == "file":
        path = resolved["path"]
        filename = os.path.basename(path)
        # Use posixpath for HuggingFace repo paths (always forward slashes)
        file_repo_path = posixpath.join(path_in_repo, filename) if path_in_repo else filename
        api.upload_file(
            path_or_fileobj=path,
            path_in_repo=file_repo_path,
            repo_id=repo_id,
            repo_type=repo_type,
            commit_message=commit_message,
            revision=revision,
        )
        uploaded_files = 1
        ctx.log_message(f"Uploaded file: {filename}")

    elif resolved["type"] == "data":
        # Save data to temp file and upload
        data = resolved["data"]
        temp_path = os.path.join(ctx.run_dir, "upload_data.json")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)

        filename = "data.json"
        if repo_type == "dataset":
            # For datasets, try to upload as a more useful format
            if isinstance(data, list) and all(isinstance(r, dict) for r in data):
                try:
                    import csv as csv_mod
                    import io
                    headers = list(data[0].keys()) if data else []
                    buf = io.StringIO()
                    writer = csv_mod.writer(buf)
                    writer.writerow(headers)
                    for row in data:
                        writer.writerow([row.get(h, "") for h in headers])
                    temp_path = os.path.join(ctx.run_dir, "data.csv")
                    with open(temp_path, "w", encoding="utf-8", newline="") as f:
                        f.write(buf.getvalue())
                    filename = "data.csv"
                except Exception:
                    ctx.log_message("WARNING: Could not convert to CSV, uploading as JSON")

        # Use posixpath for HuggingFace repo paths (always forward slashes)
        file_repo_path = posixpath.join(path_in_repo, filename) if path_in_repo else filename
        api.upload_file(
            path_or_fileobj=temp_path,
            path_in_repo=file_repo_path,
            repo_id=repo_id,
            repo_type=repo_type,
            commit_message=commit_message,
            revision=revision,
        )
        uploaded_files = 1
        ctx.log_message(f"Uploaded data as {filename}")

    else:
        raise BlockInputError(
            f"Cannot determine how to upload data of type: {resolved['type']}",
            details=f"Upstream block produced: {str(raw_data)[:200]}",
            recoverable=False,
        )

    # ---- Finalize ----
    ctx.report_progress(4, 4)
    ctx.log_message(f"Push complete: {repo_url}")

    ctx.save_output("repo_url", repo_url)
    ctx.save_output("summary", {
        "repo_id": repo_id,
        "repo_type": repo_type,
        "files_uploaded": uploaded_files,
        "private": private,
        "revision": revision,
    })
    ctx.log_metric("files_uploaded", float(uploaded_files))

    ctx.log_message("HF Hub Push complete.")
