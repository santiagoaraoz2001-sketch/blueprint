# Troubleshooting

## Server Not Starting

### Symptom

Running `uvicorn backend.main:app` fails or the server exits immediately.

### Common Causes and Fixes

**Port already in use:**

```
ERROR: [Errno 48] Address already in use
```

Another process is using port 8000. Either stop that process or use a different port:

```bash
uvicorn backend.main:app --port 8001
```

**Missing dependencies:**

```
ModuleNotFoundError: No module named 'fastapi'
```

Ensure your virtual environment is activated and dependencies are installed:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

**Database errors:**

If the SQLite database is corrupted, you can reset it by removing the database file. This will delete all saved projects and runs:

```bash
rm ~/.specific-labs/specific.db
```

Blueprint will recreate the database on the next startup.

## Blocks Failing During Execution

### Symptom

A block turns red during pipeline execution and the run stops.

### Diagnosis

1. Open the monitor panel (**Cmd+Shift+M**) to see the error message and stack trace.
2. Check the run diagnostics at **System > Diagnostics** for detailed event logs.
3. Look at the structured log file at `~/.specific-labs/logs/blueprint.jsonl` for more context.

### Common Causes

**Missing Python package:**

The block imports a package that is not installed. Go to **System > Dependencies** to see which packages are missing and install them directly from the UI.

**Invalid input data:**

A block received data in an unexpected format. Check that upstream blocks are producing the correct output type. Verify that port types match between connected blocks.

**File not found:**

A Dataset Loader or file-based block cannot find the specified file path. Ensure the file exists and the path is absolute or relative to the data directory.

**Out of memory:**

Large datasets or models may exhaust system RAM. Check the monitor panel for memory usage. Consider reducing batch sizes, using data sampling, or processing data in chunks.

## Port Compatibility Errors

### Symptom

You cannot connect two blocks, or a connection shows a red warning.

### Explanation

Ports are typed. A `dataframe` output cannot connect to a `tensor` input directly. Check the port types by hovering over the ports to see their types.

### Fixes

- Insert a conversion block between incompatible ports (e.g., a DataFrame-to-Tensor converter).
- Change the output port type in a custom block's `block.yaml` if the data is actually compatible.
- Use an `any` typed port if you need maximum flexibility (but lose type safety).

## GPU Not Detected

### Symptom

The hardware profile shows no GPU, or GPU-accelerated blocks fall back to CPU.

### Diagnosis

Check the hardware profile at **System > Hardware** to see what Blueprint detected.

### Fixes

**NVIDIA GPU (CUDA):**

Ensure CUDA toolkit and appropriate drivers are installed:

```bash
nvidia-smi                    # Verify driver is working
python -c "import torch; print(torch.cuda.is_available())"
```

If CUDA is not detected, install or update your NVIDIA drivers and the CUDA toolkit.

**Apple Silicon (Metal):**

Metal acceleration is available on macOS 12+ with Apple Silicon. Ensure you are using a Python build that supports Metal:

```bash
python -c "import torch; print(torch.backends.mps.is_available())"
```

**ROCm (AMD):**

ROCm support requires compatible AMD GPUs and the ROCm toolkit. Check the ROCm documentation for supported hardware.

## Pipeline Validation Errors

### Symptom

The pipeline cannot be saved or run due to validation errors displayed in the status bar.

### Common Validation Issues

**Cycle detected:**

Your pipeline contains a circular dependency. Pipelines must be directed acyclic graphs (DAGs). Trace the connections and remove the edge that creates the cycle.

**Disconnected required input:**

A block has a required input port with no incoming connection. Either connect a source block or remove the block from the pipeline.

**Missing required parameter:**

A block has a required parameter with no value set. Click on the block and fill in the required fields in the configuration panel.

**Duplicate block names:**

Two blocks have the same display name. While this does not prevent execution, it can cause confusion in logs and results. Rename one of the blocks.

## Frontend Not Loading

### Symptom

The browser shows a blank page or "Frontend dist folder not found" error.

### Fixes

Ensure the frontend has been built:

```bash
cd frontend
npm install
npm run build
```

For development, run the Vite dev server alongside the backend:

```bash
cd frontend
npm run dev
```

Verify the browser is pointed at the correct URL (default: `http://localhost:5173` for dev, `http://localhost:8000` for production build).

## Getting More Help

- Check the structured logs at `~/.specific-labs/logs/blueprint.jsonl` for detailed event data.
- Use **System > Diagnostics** with a run ID to see the full event timeline for a specific run.
- Review the dependency check at **System > Dependencies** to ensure all required packages are installed.
- Visit the project repository for open issues and community discussions.
