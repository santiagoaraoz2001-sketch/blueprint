# Running Pipelines

## How to Run a Pipeline

There are several ways to start a pipeline run:

1. **Run button:** Click the **Run** button in the pipeline editor toolbar.
2. **Keyboard shortcut:** Press **Cmd+Shift+R** to re-run the pipeline.
3. **Command palette:** Press **Cmd+K** and type "Run" to find run commands.

Before execution begins, Blueprint validates the pipeline. If there are validation errors (missing connections, invalid parameters, cycles), they are displayed and the run is blocked until you fix them.

## Execution Order

Blocks execute in topological order based on the pipeline DAG. A block runs only after all its input dependencies have completed. Independent branches can execute in parallel if parallel execution mode is enabled in the pipeline settings.

Blueprint uses resource-aware scheduling to determine how many blocks can run concurrently based on your hardware profile (CPU cores, available memory, GPU).

## Monitoring Progress

### Status Indicators

While a pipeline is running, each block on the canvas shows its current status:

- **Pending** (gray): Waiting for upstream blocks to finish.
- **Running** (blue, animated): Currently executing.
- **Completed** (green): Finished successfully.
- **Failed** (red): Encountered an error.

### Output Panel

Open the monitor panel with **Cmd+Shift+M** to see:

- Live log output from the currently running block.
- Elapsed time per block.
- Memory and CPU usage graphs.
- Error messages and stack traces for failed blocks.

### SSE Events

Blueprint uses Server-Sent Events (SSE) to stream real-time updates to the frontend. The SSE stream delivers:

- `block_started` — A block began executing.
- `block_progress` — Intermediate progress (e.g., epoch completion, percentage).
- `block_completed` — A block finished successfully with output summary.
- `block_failed` — A block encountered an error.
- `run_completed` — The entire pipeline run finished.
- `run_failed` — The pipeline run was aborted due to an error.

The frontend uses these events to update the canvas status indicators and output panel in real time.

## Run History

Every pipeline run is recorded in the database with:

- Run ID and timestamp.
- Status (completed, failed, cancelled).
- Duration and per-block timing.
- Input parameters used.
- Output artifacts and metrics.
- Error messages (if any).

Access run history from the **Runs** view (**Cmd+5**) to compare experiments, review past results, or re-run previous configurations.

## Re-run from Node

If a pipeline fails partway through, you do not need to re-run the entire pipeline from the beginning.

1. Right-click the block where you want to restart.
2. Select **Re-run from here** or press **Shift+R**.
3. Blueprint will reuse cached outputs from all upstream blocks and re-execute from the selected block onward.

This is especially useful for long pipelines where early blocks (data loading, preprocessing) are expensive and have not changed.

## Cancelling a Run

To stop a running pipeline:

- Click the **Stop** button in the toolbar.
- Or press **Escape** while the run is in progress.

The currently executing block is terminated and the run is marked as cancelled. Completed block outputs are preserved.

## Heartbeat and Recovery

Blueprint uses a heartbeat mechanism to detect crashed runs. If a run's process dies unexpectedly (crash, power loss, etc.), the server detects the stale heartbeat and marks the run as failed with a recovery message. This happens automatically within a few minutes.

## Tips

- Use parallel execution mode for pipelines with independent branches to reduce total run time.
- Check the **System > Hardware** panel to understand your machine's capabilities before running large experiments.
- Set reasonable timeout values to prevent runaway blocks from blocking your machine.
- Review run history to compare parameter changes across experiments.
