"""Save YAML — save pipeline configuration or data as YAML file."""

import json
import os


def _resolve_data(raw):
    """Resolve raw input to a Python object."""
    if isinstance(raw, str):
        if os.path.isfile(raw):
            with open(raw, "r", encoding="utf-8") as f:
                return json.load(f)
        if os.path.isdir(raw):
            data_file = os.path.join(raw, "data.json")
            if os.path.isfile(data_file):
                with open(data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {"value": raw}
    return raw


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
        raise ValueError("No input data provided. Connect a 'data' input.")

    data = _resolve_data(raw_data)
    ctx.log_message(f"Data type: {type(data).__name__}")

    # ---- Step 2: Serialize to YAML ----
    ctx.report_progress(2, 3)
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is not installed. Install it with: pip install pyyaml")

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
        raise FileExistsError(f"File already exists: {out_filepath}. Enable 'Overwrite Existing'.")

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
