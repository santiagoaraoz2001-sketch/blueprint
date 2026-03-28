# Configuration

## Overview

Blueprint is configured at several levels: workspace settings, project settings, pipeline configuration, block parameters, and API keys. This guide covers each level and how to manage them.

## Workspace Settings

Workspace settings are global preferences that apply across all projects. Access them from the gear icon in the top-right corner or via **Cmd+,**.

### Data Directory

By default, Blueprint stores all data under `~/.specific-labs/`. You can change this by setting the `BLUEPRINT_DATA_DIR` environment variable before starting the server:

```bash
export BLUEPRINT_DATA_DIR=/path/to/your/data
uvicorn backend.main:app --reload --port 8000
```

The data directory contains:

- `specific.db` — SQLite database for projects, runs, and metadata.
- `blocks/` — Installed block definitions.
- `custom_blocks/` — Your custom blocks.
- `pipelines/` — Saved pipeline configurations.
- `artifacts/` — Run outputs and artifacts.
- `datasets/` — Imported datasets.

### Inbox Watcher

Blueprint can watch a directory for incoming files (datasets, models) and automatically import them. Enable this in workspace settings by toggling **Watcher Enabled** and setting a root path.

### Theme and Display

- **Theme:** Light or dark mode.
- **Zoom level:** Default canvas zoom.
- **Auto-save:** Toggle automatic pipeline saving.

## Project Settings

Each project has its own settings accessible from the project header.

- **Name:** Display name for the project.
- **Description:** Optional description shown in the project list.
- **Tags:** Organize projects with tags for filtering.
- **Default pipeline:** The pipeline to open when the project is launched.

## Pipeline Configuration

Pipeline-level settings are stored alongside the pipeline definition. Configure them from the pipeline toolbar.

- **Name:** Pipeline display name.
- **Description:** What this pipeline does.
- **Execution mode:** Sequential or parallel. Parallel mode runs independent branches simultaneously when hardware allows.
- **Timeout:** Maximum run time in seconds. The run is cancelled if this limit is exceeded.
- **Retry policy:** Whether to retry failed blocks automatically and how many attempts to allow.

## Block Parameters

Each block defines its own set of configurable parameters in `block.yaml`. Common parameter types include:

| Type   | Example              | Description                          |
|--------|----------------------|--------------------------------------|
| string | `model_name`         | Free-text input                      |
| int    | `num_epochs`         | Integer value with optional min/max  |
| float  | `learning_rate`      | Decimal value with optional min/max  |
| bool   | `use_gpu`            | Toggle switch                        |
| select | `optimizer`          | Dropdown from a list of options      |
| file   | `dataset_path`       | File picker                          |
| json   | `custom_config`      | Raw JSON editor                      |

Parameters can have:

- **default:** Value used when nothing is explicitly set.
- **min / max:** Numeric bounds (for int and float types).
- **options:** List of allowed values (for select type).
- **required:** Whether the parameter must be set before running.
- **description:** Help text shown in the configuration panel.

## API Keys and Secrets

Some blocks require API keys (e.g., for cloud inference providers, HuggingFace Hub, or external services). Blueprint manages secrets securely:

1. Open **Settings > Secrets** or use the Secrets panel.
2. Click **Add Secret** and enter a name (e.g., `OPENAI_API_KEY`) and value.
3. Secrets are stored encrypted in the local database.
4. Blocks reference secrets by name — the actual value is injected at runtime.

Secrets never leave your machine and are never included in pipeline exports or shared configurations.

### Environment Variables

You can also provide configuration via environment variables:

| Variable                   | Description                              |
|----------------------------|------------------------------------------|
| `BLUEPRINT_DATA_DIR`       | Override the data directory path         |
| `OLLAMA_URL`               | Ollama inference server URL              |
| `MLX_URL`                  | MLX inference server URL                 |
| `CORS_ORIGINS`             | Allowed CORS origins (comma-separated)   |
| `BLUEPRINT_ENABLE_MARKETPLACE` | Enable the marketplace feature ("true"/"false") |
| `BLUEPRINT_HEARTBEAT_TIMEOUT`  | Stale run detection timeout in seconds  |
| `BLUEPRINT_RECOVERY_INTERVAL`  | Stale run recovery check interval       |

## Configuration Precedence

When the same setting can be defined at multiple levels, the following precedence applies (highest to lowest):

1. Block parameter override (set in the pipeline editor)
2. Pipeline configuration
3. Project settings
4. Workspace / global settings
5. Environment variables
6. Built-in defaults

## Exporting and Importing Configuration

Pipeline configurations can be exported as JSON for sharing or version control:

- **Export:** Right-click a pipeline and select **Export Pipeline**.
- **Import:** Use **File > Import Pipeline** and select a JSON file.

Exported files include block parameters and connections but exclude secrets and local file paths.
