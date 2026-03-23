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
6. Leaves the W&B run active so downstream blocks can call `wandb.log()`.

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

## W&B run lifecycle

The W&B Logger **does not** call `wandb.finish()` after initialization. This is
intentional — the run stays active so that downstream blocks (e.g. training
loops, evaluators) can call `wandb.log()` and their metrics will stream into the
same run.

Cleanup happens automatically in these cases:

- **Next pipeline execution:** `wandb.init()` finishes the previous run before
  starting a new one.
- **Plugin unload/disable:** The plugin's `unregister()` hook calls
  `wandb.finish()` on any active run.
- **Server shutdown:** wandb registers its own `atexit` handler.

If your pipeline has a definite end point you want to mark, add a downstream
block that calls `wandb.finish()` explicitly.

## Concurrency

W&B uses global process state for login credentials and the active run.  The
block serializes its `login()` and `init()` calls behind a threading lock, so
concurrent pipeline executions on the same server process will not race each
other.  This matches the pattern used by the built-in W&B export connector.

Note that only one W&B run can be active per process at a time.  If two
pipelines with W&B Logger blocks execute concurrently, the second `init()` will
finish the first run before starting its own.

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

## Testing

You can test the block without a real W&B account by mocking the `wandb`
module.  The block imports `wandb` at call time, so patching works cleanly:

```python
from unittest.mock import MagicMock, patch

mock_wandb = MagicMock()
mock_run = MagicMock()
mock_run.id = "test-run-id"
mock_run.name = "test-run"
mock_run.get_url.return_value = "https://wandb.ai/test/runs/abc"
mock_wandb.init.return_value = mock_run

with patch.dict("sys.modules", {"wandb": mock_wandb}):
    # Import and execute the block's run() with a mock BlockContext
    ...
```

Key behaviors to verify:

1. **Dependency missing:** Remove `wandb` from `sys.modules` → block raises
   `BlockDependencyError` with install hint.
2. **API key missing:** Pass empty `api_key` config → block raises
   `BlockConfigError` on the `api_key` field.
3. **Auth failure:** Make `wandb.login` raise → block raises `BlockConfigError`
   with details pointing to the authorize URL.
4. **Init failure:** Make `wandb.init` raise → block raises
   `BlockExecutionError` with connectivity hint.
5. **Passthrough:** Connect a trigger input → output `passthrough` matches the
   raw input unchanged.
6. **No trigger:** Omit trigger input → block completes without error; no
   passthrough output saved.
7. **Metric extraction:** Pass `{"loss": 0.5, "flag": True}` as trigger data →
   only `loss` is logged to W&B (booleans excluded).

## Plugin structure

```
wandb-monitor/
  plugin.yaml                          # Plugin metadata and permissions
  __init__.py                          # Plugin lifecycle hooks
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
2. **`__init__.py`** — Implement both `register()` and `unregister()` hooks.
   Use `unregister()` to clean up any global state your plugin creates.
3. **block.yaml** — Include typed `config` fields with defaults and
   descriptive `inputs`/`outputs` with `data_type` annotations.
4. **run.py** — Use `_resolve_input()` to handle file paths, directories, and
   raw data. Use `BlockDependencyError` for missing libraries,
   `BlockConfigError` for invalid configuration, and `BlockExecutionError`
   for runtime failures. Save artifacts for auditability. Report multi-step
   progress via `ctx.report_progress()`.
5. **Error handling** — Wrap external API calls in try/except and surface
   actionable error messages with recovery hints.
6. **Thread safety** — If your plugin uses libraries with global state,
   serialize access with a `threading.Lock`.
