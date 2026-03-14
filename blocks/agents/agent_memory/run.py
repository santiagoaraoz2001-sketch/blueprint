"""Agent Memory — persistent key-value store for maintaining agent context across runs."""

import json
import os
import time

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


def run(ctx):
    # ── Config ──────────────────────────────────────────────────────────
    action = ctx.config.get("action", "store")
    memory_key = ctx.config.get("key", "")
    memory_value = ctx.config.get("value", "")
    namespace = ctx.config.get("namespace", "default")
    max_entries = int(ctx.config.get("max_entries", 0))

    # Sanitize namespace to prevent path traversal
    namespace = "".join(c for c in namespace if c.isalnum() or c in ("_", "-"))
    if not namespace:
        namespace = "default"

    # ── Memory file location (persistent across runs) ───────────────────
    memory_dir = os.path.join(
        os.path.expanduser("~"), ".specific-labs", "agent_memory",
    )
    os.makedirs(memory_dir, exist_ok=True)
    memory_file = os.path.join(memory_dir, f"{namespace}.json")

    # ── Load existing memory ────────────────────────────────────────────
    memory = {}
    if os.path.isfile(memory_file):
        try:
            with open(memory_file, "r") as f:
                memory = json.load(f)
        except (json.JSONDecodeError, OSError):
            memory = {}

    ctx.log_message(f"Agent Memory: action={action}, namespace={namespace}")
    ctx.log_message(f"Current entries: {len(memory)}")

    # ── Get value from input port if not in config ──────────────────────
    if action == "store" and not memory_value:
        try:
            data = ctx.load_input("input")
            if isinstance(data, str):
                if os.path.isfile(data):
                    with open(data, "r") as f:
                        memory_value = f.read()
                else:
                    memory_value = data
            elif isinstance(data, dict):
                if memory_key and memory_key in data:
                    memory_value = data[memory_key]
                else:
                    memory_value = data
            elif isinstance(data, list):
                memory_value = data
            else:
                memory_value = str(data) if data is not None else ""
        except (ValueError, Exception):
            pass

    # ── Bulk import from dataset input ──────────────────────────────────
    bulk_count = 0
    if action == "store":
        try:
            dataset = ctx.load_input("dataset")
            records = []
            if isinstance(dataset, str) and os.path.isdir(dataset):
                data_file = os.path.join(dataset, "data.json")
                if os.path.isfile(data_file):
                    with open(data_file, "r") as f:
                        records = json.load(f)
            elif isinstance(dataset, list):
                records = dataset

            for i, record in enumerate(records):
                if isinstance(record, dict):
                    rkey = record.get("key", record.get("id", f"bulk_{i}"))
                    rval = record.get("value", record.get("text", record))
                else:
                    rkey = f"bulk_{i}"
                    rval = record
                memory[str(rkey)] = {
                    "value": rval,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "type": type(rval).__name__,
                    "source": "bulk_import",
                }
                bulk_count += 1
            if bulk_count > 0:
                ctx.log_message(f"Bulk imported {bulk_count} entries from dataset")
        except (ValueError, Exception):
            pass

    # ── Execute action ──────────────────────────────────────────────────
    result = {}

    if action == "store":
        if memory_value or bulk_count > 0:
            if memory_value:
                if not memory_key:
                    memory_key = f"entry_{len(memory)}"
                    ctx.log_message(f"No key specified, auto-key: {memory_key}")

                memory[memory_key] = {
                    "value": memory_value,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "type": type(memory_value).__name__,
                }
                ctx.log_message(
                    f"Stored: {memory_key} = {str(memory_value)[:100]}"
                )

            # LRU eviction if max_entries is set
            if max_entries > 0 and len(memory) > max_entries:
                sorted_keys = sorted(
                    memory.keys(),
                    key=lambda k: memory[k].get("timestamp", "") if isinstance(memory[k], dict) else "",
                )
                while len(memory) > max_entries:
                    evicted = sorted_keys.pop(0)
                    del memory[evicted]
                ctx.log_message(f"Evicted entries to maintain max_entries={max_entries}")

            _save_memory(memory_file, memory)
            result = {
                "action": "store",
                "key": memory_key,
                "bulk_imported": bulk_count,
                "success": True,
                "total_entries": len(memory),
            }
        else:
            ctx.log_message("Nothing to store: no value in config or input port.")
            result = {"action": "store", "success": False, "reason": "no_value"}

    elif action == "retrieve":
        if memory_key:
            entry = memory.get(memory_key)
            if entry:
                value = entry.get("value", entry) if isinstance(entry, dict) else entry
                ctx.log_message(f"Retrieved: {memory_key} = {str(value)[:100]}")
                result = {
                    "action": "retrieve",
                    "key": memory_key,
                    "value": value,
                    "found": True,
                    "timestamp": entry.get("timestamp", "") if isinstance(entry, dict) else "",
                }
            else:
                ctx.log_message(f"Key not found: {memory_key}")
                result = {
                    "action": "retrieve",
                    "key": memory_key,
                    "value": None,
                    "found": False,
                }
        else:
            # Retrieve all
            all_values = {}
            for k, v in memory.items():
                all_values[k] = v.get("value", v) if isinstance(v, dict) else v
            result = {
                "action": "retrieve_all",
                "memory": all_values,
                "count": len(all_values),
            }
            ctx.log_message(f"Retrieved all: {len(all_values)} entries")

    elif action == "clear":
        if memory_key:
            if memory_key in memory:
                del memory[memory_key]
                ctx.log_message(f"Cleared key: {memory_key}")
            else:
                ctx.log_message(f"Key not found: {memory_key}")
        else:
            cleared_count = len(memory)
            memory = {}
            ctx.log_message(f"Cleared all memory ({cleared_count} entries)")

        _save_memory(memory_file, memory)
        result = {
            "action": "clear",
            "key": memory_key or "all",
            "success": True,
            "remaining_entries": len(memory),
        }

    elif action == "list":
        entries = []
        for k, v in memory.items():
            entry_info = {"key": k}
            if isinstance(v, dict):
                entry_info["timestamp"] = v.get("timestamp", "")
                entry_info["type"] = v.get("type", "unknown")
                val = v.get("value", "")
                entry_info["preview"] = str(val)[:80]
            else:
                entry_info["preview"] = str(v)[:80]
            entries.append(entry_info)

        result = {"action": "list", "entries": entries, "count": len(entries)}
        ctx.log_message(f"Memory listing: {len(entries)} entries")
        for e in entries[:10]:
            ctx.log_message(f"  {e['key']}: {e.get('preview', '')}")
        if len(entries) > 10:
            ctx.log_message(f"  ... and {len(entries) - 10} more")

    elif action == "search":
        search_term = memory_value or memory_key
        if not search_term:
            ctx.log_message("Search requires a key or value to search for.")
            result = {"action": "search", "matches": [], "count": 0, "error": "no_search_term"}
        else:
            matches = []
            search_lower = str(search_term).lower()
            for k, v in memory.items():
                val_str = str(v.get("value", v) if isinstance(v, dict) else v).lower()
                if search_lower in k.lower() or search_lower in val_str:
                    matches.append({
                        "key": k,
                        "value": v.get("value", v) if isinstance(v, dict) else v,
                        "timestamp": v.get("timestamp", "") if isinstance(v, dict) else "",
                    })
            result = {"action": "search", "matches": matches, "count": len(matches), "query": str(search_term)}
            ctx.log_message(f"Search for '{search_term}': {len(matches)} matches")

    # ── Save outputs ────────────────────────────────────────────────────
    ctx.save_output("output", result)
    ctx.save_output("memory", memory)

    metrics = {
        "memory_entries": len(memory),
        "action": action,
        "namespace": namespace,
    }
    ctx.save_output("metrics", metrics)
    ctx.log_metric("memory_entries", len(memory))
    ctx.report_progress(1, 1)


def _save_memory(path, memory):
    """Write memory dict to disk."""
    with open(path, "w") as f:
        json.dump(memory, f, indent=2, default=str)
