# W&B Monitor Plugin

Stream metrics to Weights & Biases in real-time during Blueprint training runs.

This plugin serves as the **reference implementation** for Blueprint plugin
authors. It demonstrates how to structure a plugin, declare blocks with schemas,
handle external dependencies, and integrate with the block SDK.

## Installation

1. Install the `wandb` dependency:

```bash
pip install wandb>=0.16.0
```

2. Copy the plugin into your plugins directory:

```bash
cp -r examples/plugins/wandb-monitor ~/.specific-labs/plugins/wandb-monitor
```

3. Store your W&B API key as a Blueprint secret:

```
Settings > Secrets > Add "wandb_api_key"
```

Alternatively, pass the key directly in the block config field.

## Usage

Wire the **W&B Logger** block into your pipeline **before** any training or
evaluation blocks. It initializes a W&B run and forwards all input data
unchanged, so it can be inserted inline without disrupting existing connections.

### Pipeline wiring

```
[Data Loader] --> [W&B Logger] --> [Training Block] --> [Evaluation]
```

The W&B Logger block:

1. Authenticates with W&B using the provided API key.
2. Initializes a new run under the specified project and entity.
3. Passes trigger data through to the `passthrough` output unmodified.
4. Logs any numeric metrics found in the trigger data to W&B.
5. Emits the W&B run URL on the `wandb_run_url` output port.
6. Leaves the W&B run open so downstream blocks can log to it.

### Block configuration

| Field                | Type    | Default       | Description                                  |
|----------------------|---------|---------------|----------------------------------------------|
| `api_key`            | string  | *(required)*  | W&B API key or `$secret:wandb_api_key`       |
| `project`            | string  | `blueprint`   | W&B project name                             |
| `entity`             | string  | `""`          | W&B team or username (blank = personal)      |
| `run_name`           | string  | `""`          | Custom run name (blank = auto-generated)     |
| `log_system_metrics` | boolean | `true`        | Log CPU, memory, and GPU utilization         |

### Outputs

| Port             | Data Type | Description                                         |
|------------------|-----------|-----------------------------------------------------|
| `passthrough`    | any       | Trigger data forwarded unchanged to downstream      |
| `wandb_run_url`  | text      | URL of the live W&B dashboard for this run          |

### Artifacts

Each execution saves a `wandb_run_status.json` artifact containing the run ID,
run name, project, entity, and URL — useful for auditing and cross-referencing
pipeline executions with W&B dashboards.

## Troubleshooting

### API key errors

- Verify the key at https://wandb.ai/authorize
- When using secrets: confirm `wandb_api_key` is set in Settings > Secrets
- The `$secret:wandb_api_key` syntax is resolved automatically by the executor

### Network issues

- The plugin requires outbound HTTPS access to `api.wandb.ai`
- Check firewall rules if running in a restricted environment
- Set the `WANDB_MODE=offline` environment variable as a fallback for
  air-gapped environments; metrics will sync when connectivity is restored

### Missing dependency

If you see a `BlockDependencyError` mentioning `wandb`, install it:

```bash
pip install wandb>=0.16.0
```

### Run not appearing in W&B

- Ensure the project name matches an existing project, or that your API key
  has permission to create new projects
- Check that the entity matches your W&B team name exactly (case-sensitive)
- Look for authentication errors in the block's live log panel

## Plugin structure

```
wandb-monitor/
  plugin.yaml                          # Plugin metadata and permissions
  __init__.py                          # Plugin registration hook
  blocks/
    flow/
      wandb_logger/
        block.yaml                     # Block schema (inputs, outputs, config)
        run.py                         # Block execution logic
  README.md
```

## Writing your own plugin

Use this plugin as a template. Key patterns to follow:

1. **plugin.yaml** — Declare `permissions` for any capabilities your plugin
   needs (e.g., `network`, `secrets`, `filesystem`).
2. **block.yaml** — Include `version`, typed `config` fields with defaults,
   and descriptive `inputs`/`outputs` with `data_type` annotations.
3. **run.py** — Use `_resolve_input()` to handle file paths, directories, and
   raw data. Use `BlockDependencyError` for missing libraries and
   `BlockConfigError` for invalid configuration. Save artifacts for
   auditability. Report multi-step progress via `ctx.report_progress()`.
4. **Error handling** — Wrap external API calls in try/except and surface
   actionable error messages with recovery hints.
