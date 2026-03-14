"""Rollback Point — create a state snapshot for downstream failure recovery."""

import json
import os
from datetime import datetime, timezone


def run(ctx):
    label = ctx.config.get("label", "rollback-1")
    auto_rollback_on_failure = ctx.config.get("auto_rollback_on_failure", True)
    max_snapshots = int(ctx.config.get("max_snapshots", 3))
    snapshot_metadata = ctx.config.get("snapshot_metadata", "").strip()

    ctx.log_message(f"Rollback Point [{label}]: creating snapshot")
    ctx.report_progress(0, 3)

    # ---- Step 1: Load input data ----
    ctx.report_progress(1, 3)
    raw_data = ctx.resolve_as_data("data")
    if not raw_data:
        raise ValueError("No data provided. Connect a 'data' input.")
    data = raw_data

    # ---- Step 2: Create snapshot ----
    ctx.report_progress(2, 3)
    now = datetime.now(timezone.utc)
    snapshot_id = f"{label}_{now.strftime('%Y%m%d_%H%M%S')}"

    # Create snapshots directory
    snapshots_dir = os.path.join(ctx.run_dir, "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)

    # Save snapshot
    snapshot_path = os.path.join(snapshots_dir, f"{snapshot_id}.json")
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)

    # Note: resolve_as_data already loads file contents into memory,
    # so raw_data is always a list/dict — the file copy is captured in the JSON snapshot above.

    # Manage snapshot count — remove oldest if over limit
    existing_snapshots = sorted([
        f for f in os.listdir(snapshots_dir)
        if f.startswith(label) and f.endswith(".json")
    ])
    while len(existing_snapshots) > max_snapshots:
        oldest = existing_snapshots.pop(0)
        oldest_path = os.path.join(snapshots_dir, oldest)
        os.remove(oldest_path)
        ctx.log_message(f"Removed old snapshot: {oldest}")

    # Write snapshot index
    index_path = os.path.join(snapshots_dir, "snapshot_index.json")
    index = {}
    if os.path.isfile(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            try:
                index = json.load(f)
            except json.JSONDecodeError:
                index = {}

    # Parse snapshot metadata (key: value per line)
    metadata = {}
    if snapshot_metadata:
        for line in snapshot_metadata.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                metadata[k.strip()] = v.strip()

    if "snapshots" not in index:
        index["snapshots"] = []
    snapshot_entry = {
        "id": snapshot_id,
        "label": label,
        "path": snapshot_path,
        "created_at": now.isoformat(),
        "data_type": type(data).__name__,
        "data_size": len(data) if isinstance(data, (list, dict, str)) else None,
    }
    if metadata:
        snapshot_entry["metadata"] = metadata
    index["snapshots"].append(snapshot_entry)
    # Trim index to max_snapshots
    index["snapshots"] = index["snapshots"][-max_snapshots:]
    index["latest"] = snapshot_id
    index["auto_rollback_on_failure"] = auto_rollback_on_failure

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, default=str, ensure_ascii=False)

    ctx.log_message(f"Snapshot created: {snapshot_id}")
    ctx.log_message(f"Snapshot path: {snapshot_path}")
    ctx.log_message(f"Total snapshots for '{label}': {len(existing_snapshots) + 1}")

    # ---- Step 3: Check for rollback request ----
    ctx.report_progress(3, 3)

    # Check if a rollback was requested (by a downstream block writing a rollback_request.json)
    rollback_request_path = os.path.join(ctx.run_dir, "rollback_request.json")
    rolled_back = False
    restored_data = data  # Default: pass through current data

    if os.path.isfile(rollback_request_path):
        try:
            with open(rollback_request_path, "r", encoding="utf-8") as f:
                request = json.load(f)
            target_id = request.get("target_snapshot", "latest")

            if target_id == "latest" and index.get("snapshots"):
                # Restore from latest snapshot before the current one
                if len(index["snapshots"]) >= 2:
                    restore_entry = index["snapshots"][-2]
                else:
                    restore_entry = index["snapshots"][-1]
            else:
                # Find specific snapshot
                restore_entry = None
                for entry in index["snapshots"]:
                    if entry["id"] == target_id:
                        restore_entry = entry
                        break

            if restore_entry and os.path.isfile(restore_entry["path"]):
                with open(restore_entry["path"], "r", encoding="utf-8") as f:
                    restored_data = json.load(f)
                rolled_back = True
                ctx.log_message(f"ROLLBACK: restored from snapshot '{restore_entry['id']}'")
            else:
                ctx.log_message("WARNING: rollback requested but snapshot not found")
        except (json.JSONDecodeError, KeyError) as e:
            ctx.log_message(f"WARNING: rollback request malformed: {e}")

    # Save outputs
    snapshot_info = {
        "snapshot_id": snapshot_id,
        "label": label,
        "snapshot_path": snapshot_path,
        "rolled_back": rolled_back,
        "auto_rollback_on_failure": auto_rollback_on_failure,
        "total_snapshots": len(index.get("snapshots", [])),
        "created_at": now.isoformat(),
    }

    # "output" port forwards the data (restored or current)
    ctx.save_output("output", restored_data)

    # "snapshot" port provides the snapshot metadata
    ctx.save_output("snapshot", snapshot_info)

    ctx.save_artifact("snapshot_index", index_path)
    ctx.log_metric("rolled_back", 1.0 if rolled_back else 0.0)
    ctx.log_metric("snapshot_count", len(index.get("snapshots", [])))

    if rolled_back:
        ctx.log_message("Rollback Point complete (data RESTORED from snapshot)")
    else:
        ctx.log_message("Rollback Point complete (snapshot saved, data passed through)")
