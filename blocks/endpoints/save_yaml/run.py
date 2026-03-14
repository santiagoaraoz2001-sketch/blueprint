"""Save YAML — save pipeline configuration or data as YAML file."""

import csv as csv_mod
import json
import os

from backend.block_sdk.exceptions import BlockDependencyError, BlockInputError


def _read_jsonl(f):
    """Read JSONL file with per-line error handling."""
    records = []
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"_raw_line": line, "_parse_error": True})
    return records


def _resolve_data(raw):
    """Resolve raw input to a Python object, handling any upstream format."""
    if isinstance(raw, str):
        if os.path.isfile(raw):
            ext = os.path.splitext(raw)[1].lower()
            try:
                if ext == ".jsonl":
                    with open(raw, "r", encoding="utf-8", errors="replace") as f:
                        return _read_jsonl(f)
                elif ext in (".json",):
                    with open(raw, "r", encoding="utf-8") as f:
                        return json.load(f)
                elif ext == ".csv":
                    with open(raw, "r", encoding="utf-8", errors="replace") as f:
                        return list(csv_mod.DictReader(f))
                elif ext in (".yaml", ".yml"):
                    try:
                        import yaml
                        with open(raw, "r", encoding="utf-8") as f:
                            result = yaml.safe_load(f)
                            return result if result is not None else {}
                    except ImportError:
                        with open(raw, "r", encoding="utf-8", errors="replace") as f:
                            return {"value": f.read()}
                else:
                    with open(raw, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    try:
                        return json.loads(content)
                    except (json.JSONDecodeError, ValueError):
                        return {"value": content}
            except (UnicodeDecodeError, json.JSONDecodeError):
                return {"value": f"<unreadable file: {os.path.basename(raw)}>"}
        if os.path.isdir(raw):
            for name in ("data.json", "results.json", "output.json", "data.csv", "data.yaml"):
                fpath = os.path.join(raw, name)
                if os.path.isfile(fpath):
                    return _resolve_data(fpath)
            try:
                files = [f for f in os.listdir(raw) if not f.startswith(".")]
            except OSError:
                files = []
            return {"directory": raw, "files": files}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {"value": raw}
    if isinstance(raw, (dict, list)):
        return raw
    return {"value": str(raw)}


def run(ctx):
    output_path = ctx.config.get("output_path", "./output").strip()
    filename = ctx.config.get("filename", "config.yaml").strip()
    default_flow_style = ctx.config.get("default_flow_style", False)
    sort_keys = ctx.config.get("sort_keys", False)
    overwrite = ctx.config.get("overwrite_existing", True)
    allow_unicode = ctx.config.get("allow_unicode", True)
    timestamp_filename = ctx.config.get("timestamp_filename", False)
    header_comment = ctx.config.get("header_comment", "").strip()

    ctx.log_message("Save YAML starting")
    ctx.report_progress(0, 3)

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 3)
    raw_data = ctx.load_input("data")
    if raw_data is None:
        raise BlockInputError(
            "No input data provided. Connect a 'data' input.",
            recoverable=False,
        )

    data = _resolve_data(raw_data)
    ctx.log_message(f"Data type: {type(data).__name__}")

    # ---- Step 2: Serialize to YAML ----
    ctx.report_progress(2, 3)
    try:
        import yaml
    except ImportError as e:
        missing = getattr(e, "name", None) or "pyyaml"
        raise BlockDependencyError(
            missing,
            "PyYAML is required for YAML output",
            install_hint="pip install pyyaml",
        )

    content = yaml.dump(
        data,
        default_flow_style=default_flow_style,
        sort_keys=sort_keys,
        allow_unicode=allow_unicode,
        indent=2,
    )

    # ---- Step 3: Write file ----
    if os.path.isabs(output_path):
        out_dir = output_path
    else:
        out_dir = os.path.join(ctx.run_dir, output_path)
    os.makedirs(out_dir, exist_ok=True)

    if not (filename.endswith(".yaml") or filename.endswith(".yml")):
        filename += ".yaml"

    # Apply timestamp to filename
    if timestamp_filename:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base, fext = os.path.splitext(filename)
        filename = f"{base}_{ts}{fext}"

    out_filepath = os.path.join(out_dir, filename)

    if os.path.exists(out_filepath) and not overwrite:
        raise BlockInputError(
            f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.",
            recoverable=True,
        )

    with open(out_filepath, "w", encoding="utf-8") as f:
        if header_comment:
            for line in header_comment.splitlines():
                f.write(f"# {line}\n")
            f.write("\n")
        f.write(content)

    ctx.report_progress(3, 3)
    file_size = os.path.getsize(out_filepath)
    ctx.log_message(f"Saved YAML to {out_filepath} ({file_size:,} bytes)")

    ctx.save_output("file_path", out_filepath)
    ctx.save_output("summary", {"file_size_bytes": file_size})
    ctx.save_artifact("yaml_output", out_filepath)
    ctx.log_metric("file_size_bytes", float(file_size))

    ctx.log_message("Save YAML complete.")
