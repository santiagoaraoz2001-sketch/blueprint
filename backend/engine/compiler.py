import json
from .executor import _topological_sort, _find_block_module
from ..config import BUILTIN_BLOCKS_DIR
from pathlib import Path

def compile_pipeline_to_python(pipeline_name: str, definition: dict) -> str:
    """Compiles a Blueprint pipeline definition into an executable Python script."""
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    if not nodes:
        return "# Empty pipeline definition - nothing to compile."

    order = _topological_sort(nodes, edges)
    node_map = {n["id"]: n for n in nodes}

    # Pre-scan for missing blocks so we can skip them cleanly
    missing_blocks: set[str] = set()
    block_dirs: dict[str, Path] = {}
    for node_id in order:
        node = node_map.get(node_id)
        if not node or node.get("type") in ("groupNode", "stickyNote"):
            continue
        node_data = node.get("data", {})
        block_type = node_data.get("type", "")
        block_dir_path = _find_block_module(block_type)
        if block_dir_path:
            block_dirs[node_id] = block_dir_path
        else:
            missing_blocks.add(node_id)

    script_lines = [
        "#!/usr/bin/env python3",
        f'"""',
        f'Ejected Blueprint Pipeline: {pipeline_name}',
        f'Generated from Blueprint Workbench.',
        f'',
        f'WARNING: This script references block directories on the machine where it was',
        f'generated. The block_dir paths are absolute and may not exist on other machines.',
        f'To make this portable, copy the referenced block directories alongside this script',
        f'and update the paths accordingly.',
        f'"""',
        "",
        "import os",
        "import sys",
        "import uuid",
        "import importlib.util",
        "import traceback",
        "from typing import Any, Optional",
        "",
        "# Ensure blocks/ parent is on sys.path so cross-block imports work",
        "# (e.g. `from blocks.inference._inference_utils import ...`)",
        f"_BLOCKS_PARENT = r'{str(BUILTIN_BLOCKS_DIR.parent)}'",
        "if os.path.isdir(_BLOCKS_PARENT) and _BLOCKS_PARENT not in sys.path:",
        "    sys.path.insert(0, _BLOCKS_PARENT)",
        "",
        "class BlockContext:",
        "    def __init__(self, run_dir: str, block_dir: str, config: dict, inputs: dict, project_name: str='', experiment_name: str=''):",
        "        self.run_dir = run_dir",
        "        self.block_dir = block_dir",
        "        self.config = config",
        "        self.inputs = inputs",
        "        self._inputs = inputs",
        "        self.project_name = project_name",
        "        self.experiment_name = experiment_name",
        "        self._outputs = {}",
        "        self._metrics = {}",
        "        os.makedirs(run_dir, exist_ok=True)",
        "    def load_input(self, name: str) -> Any:",
        "        if name not in self.inputs:",
        "            raise ValueError(f\"Input '{name}' not connected\")",
        "        return self.inputs[name]",
        "    def log_message(self, msg: str): print(f'  [LOG] {msg}')",
        "    def log_metric(self, name: str, value: float, step=None):",
        "        self._metrics[name] = value",
        "        print(f'  [METRIC] {name} = {value}')",
        "    def report_progress(self, current: int, total: int):",
        "        pct = int(current / total * 100) if total > 0 else 0",
        "        print(f'  [PROGRESS] {pct}% ({current}/{total})')",
        "    def save_output(self, name: str, data: Any): self._outputs[name] = data",
        "    def save_artifact(self, name: str, path: str): print(f'  [ARTIFACT] {name} -> {path}')",
        "    def get_outputs(self): return self._outputs",
        "    def get_metrics(self): return self._metrics",
        "",
        "def load_block_run_function(block_dir: str):",
        "    run_py = os.path.join(block_dir, 'run.py')",
        "    if not os.path.exists(run_py):",
        "        raise FileNotFoundError(f'Block run.py not found at {run_py}')",
        "    spec = importlib.util.spec_from_file_location('block_module', run_py)",
        "    module = importlib.util.module_from_spec(spec)",
        "    spec.loader.exec_module(module)",
        "    return module.run",
        "",
        "def execute_pipeline():",
        "    run_id = str(uuid.uuid4())",
        "    base_run_dir = os.path.join(os.getcwd(), 'artifacts', run_id)",
        f"    print(f'\\n{'='*60}')",
        f"    print(f'  Blueprint Pipeline: {pipeline_name}')",
        f"    print(f'{'='*60}')",
        "    print(f'Run ID:     {run_id}')",
        "    print(f'Artifacts:  {base_run_dir}')",
    ]

    # Count executable blocks
    executable_count = sum(
        1 for nid in order
        if node_map.get(nid)
        and node_map[nid].get("type") not in ("groupNode", "stickyNote")
        and nid not in missing_blocks
    )
    script_lines.append(f"    print(f'Blocks:     {executable_count}')")
    script_lines.extend([
        "    print()",
        "",
        "    # Dictionary to store outputs connected by handles",
        "    outputs = {}",
        "    failed_blocks = []",
        "    completed_blocks = []",
        ""
    ])

    block_idx = 0
    for node_id in order:
        node = node_map.get(node_id)
        if not node:
            continue

        if node.get("type") in ("groupNode", "stickyNote"):
            continue

        node_data = node.get("data", {})
        block_type = node_data.get("type", "")
        label = node_data.get("label", block_type)
        config = node_data.get("config", {})

        # Skip missing blocks entirely — don't reference undefined variables
        if node_id in missing_blocks:
            script_lines.append(f"    # SKIPPED: Block '{label}' ({block_type}) — run.py not found on this machine")
            script_lines.append(f"    print('⚠ Skipping block: {label} ({block_type}) — module not found')")
            script_lines.append("")
            continue

        block_dir_path = block_dirs[node_id]
        block_idx += 1

        # Clean ID for python variable
        safe_id = f"node_{node_id.replace('-', '_')}"

        script_lines.extend([
            f"    # --- Block {block_idx}: {label} ({block_type}) ---",
            f"    print(f'➜ [{block_idx}/{executable_count}] Running: {label} ({block_type})')",
            f"    try:",
            f"        inputs_{safe_id} = {{}}"
        ])

        # Resolve inputs — collect multiple edges to same handle into a list
        # First, group edges by target handle
        edges_by_handle: dict[str, list[dict]] = {}
        for edge in edges:
            if edge.get("target") == node_id:
                tgt_handle = edge.get("targetHandle", "")
                if tgt_handle not in edges_by_handle:
                    edges_by_handle[tgt_handle] = []
                edges_by_handle[tgt_handle].append(edge)

        for tgt_handle, handle_edges in edges_by_handle.items():
            if len(handle_edges) == 1:
                # Single connection — pass value directly
                edge = handle_edges[0]
                src_id = edge.get("source", "")
                src_handle = edge.get("sourceHandle", "")
                safe_src_id = f"node_{src_id.replace('-', '_')}"

                # Skip edges from missing/skipped blocks
                if src_id in missing_blocks:
                    script_lines.append(f"        # Skipped: input from missing block '{src_id}'")
                    continue

                script_lines.append(f"        if '{src_handle}' in outputs.get('{safe_src_id}', {{}}):")
                script_lines.append(f"            inputs_{safe_id}['{tgt_handle}'] = outputs['{safe_src_id}']['{src_handle}']")
            else:
                # Multiple connections — collect into a list
                script_lines.append(f"        # Multiple connections to input '{tgt_handle}' — merging into list")
                script_lines.append(f"        _multi_{safe_id}_{tgt_handle} = []")
                for edge in handle_edges:
                    src_id = edge.get("source", "")
                    src_handle = edge.get("sourceHandle", "")
                    safe_src_id = f"node_{src_id.replace('-', '_')}"

                    if src_id in missing_blocks:
                        script_lines.append(f"        # Skipped: input from missing block '{src_id}'")
                        continue

                    script_lines.append(f"        if '{src_handle}' in outputs.get('{safe_src_id}', {{}}):")
                    script_lines.append(f"            _multi_{safe_id}_{tgt_handle}.append(outputs['{safe_src_id}']['{src_handle}'])")
                script_lines.append(f"        if _multi_{safe_id}_{tgt_handle}:")
                script_lines.append(f"            inputs_{safe_id}['{tgt_handle}'] = _multi_{safe_id}_{tgt_handle}")

        # Stringify config — escape special characters for safe embedding
        config_str = json.dumps(config, indent=8).replace('\\n', '\\n        ')

        # Escape backslashes in block_dir_path for Windows compatibility
        block_dir_str = str(block_dir_path).replace('\\', '\\\\')

        script_lines.extend([
            f"        ctx_{safe_id} = BlockContext(",
            f"            run_dir=os.path.join(base_run_dir, '{node_id}'),",
            f"            block_dir=r'{block_dir_str}',",
            f"            config={config_str},",
            f"            inputs=inputs_{safe_id},",
            f"            project_name='Ejected',",
            f"            experiment_name='Ejected Run'",
            f"        )",
            f"        run_{safe_id} = load_block_run_function(r'{block_dir_str}')",
            f"        run_{safe_id}(ctx_{safe_id})",
            f"        outputs['{safe_id}'] = ctx_{safe_id}.get_outputs()",
            f"        completed_blocks.append('{label}')",
            f"        output_keys = list(ctx_{safe_id}.get_outputs().keys())",
            f"        print(f'  ✓ Completed — outputs: {{output_keys}}')",
            f"    except Exception as e:",
            f"        print(f'  ✗ FAILED: {{e}}')",
            f"        traceback.print_exc()",
            f"        failed_blocks.append(('{label}', str(e)))",
            f"        print(f'  Continuing pipeline execution...')",
            ""
        ])

    # Execution summary
    script_lines.extend([
        f"    # --- Execution Summary ---",
        f"    print()",
        f"    print('{'='*60}')",
        f"    print('  EXECUTION SUMMARY')",
        f"    print('{'='*60}')",
        f"    print(f'  Completed: {{len(completed_blocks)}}/{executable_count} blocks')",
        "    if failed_blocks:",
        "        print(f'  Failed:    {len(failed_blocks)} blocks')",
        "        for name, err in failed_blocks:",
        "            print(f'    ✗ {name}: {err}')",
        "    if not failed_blocks:",
        "        print('  Status:    ✓ All blocks completed successfully')",
        "    else:",
        "        print('  Status:    ⚠ Some blocks failed (see above)')",
        "    print(f'  Artifacts: {base_run_dir}')",
        "    print()",
        "",
        "    # Return output keys for programmatic use",
        "    return outputs",
        "",
        "if __name__ == '__main__':",
        "    result = execute_pipeline()",
        "    if result:",
        "        print(f'Output keys: {list(result.keys())}')",
        ""
    ])

    return "\n".join(script_lines)
