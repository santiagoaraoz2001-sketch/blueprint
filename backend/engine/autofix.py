"""AutofixEngine — proposes and applies deterministic repairs for pipeline validation errors.

Instead of telling users 'your graph has 12 errors', this engine maps validation
error messages to safe repair actions with preview and undo support.

Each fix is an AutofixPatch: a self-contained, deterministic mutation that can
be previewed (before/after), selectively applied, and reverted.
"""

from __future__ import annotations

import copy
import logging
import re
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Literal

from ..services.registry import BlockRegistryService

logger = logging.getLogger(__name__)


@dataclass
class AutofixPatch:
    """A single proposed fix for a validation error."""

    patch_id: str
    node_id: str
    field: str
    action: Literal["set", "rename", "delete", "add_edge", "insert_converter"]
    old_value: Any
    new_value: Any
    reason: str
    confidence: Literal["high", "medium"]

    # Extra metadata for edge mutations
    edge_id: str | None = None
    source_id: str | None = None
    target_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AutofixResult:
    """Result of proposing or applying fixes."""

    patches: list[AutofixPatch] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "patches": [p.to_dict() for p in self.patches],
            "applied": self.applied,
            "skipped": [s for s in self.skipped],
        }


class AutofixEngine:
    """Maps validation errors to deterministic repair actions.

    Usage:
        engine = AutofixEngine(registry)
        patches = engine.propose_fixes(errors, warnings, nodes, edges)
        nodes, edges = engine.apply_fixes([p.patch_id for p in patches], nodes, edges)
    """

    def __init__(self, registry: BlockRegistryService) -> None:
        self._registry = registry

    def propose_fixes(
        self,
        errors: list[str],
        warnings: list[str],
        pipeline_nodes: list[dict],
        pipeline_edges: list[dict],
    ) -> list[AutofixPatch]:
        """Analyze validation errors and propose deterministic fixes.

        Supported fix categories:
        1. Stale handle (port renamed) -> remap edge to canonical port ID
        2. Renamed block_type -> update node.data.block_type
        3. Missing required config with known default -> apply schema default
        4. Incompatible connection -> suggest inserting a converter block (medium)
        5. Missing required connection -> suggest most compatible upstream block (medium)
        """
        patches: list[AutofixPatch] = []
        node_map = {n["id"]: n for n in pipeline_nodes}

        # Process all error and warning messages
        all_messages = [(msg, "error") for msg in errors] + [(msg, "warning") for msg in warnings]

        for msg, severity in all_messages:
            new_patches = []

            # 1. Stale handle — port renamed / non-existent output port
            new_patches.extend(self._fix_stale_output_handle(msg, node_map, pipeline_edges))
            new_patches.extend(self._fix_stale_input_handle(msg, node_map, pipeline_edges))

            # 2. Outdated block ports (version mismatch)
            new_patches.extend(self._fix_outdated_ports(msg, node_map, pipeline_edges))

            # 3. Missing required config with default
            new_patches.extend(self._fix_missing_config(msg, node_map))

            # 4. Incompatible connection
            new_patches.extend(self._fix_incompatible_connection(msg, node_map, pipeline_edges))

            # 5. Missing required input connection
            new_patches.extend(self._fix_missing_required_input(msg, node_map, pipeline_nodes, pipeline_edges))

            patches.extend(new_patches)

        # Deduplicate patches by (node_id, field, action, new_value)
        seen: set[tuple] = set()
        unique: list[AutofixPatch] = []
        for p in patches:
            key = (p.node_id, p.field, p.action, str(p.new_value))
            if key not in seen:
                seen.add(key)
                unique.append(p)

        return unique

    def apply_fixes(
        self,
        patch_ids: list[str],
        pipeline_nodes: list[dict],
        pipeline_edges: list[dict],
        all_patches: list[AutofixPatch] | None = None,
    ) -> tuple[list[dict], list[dict], AutofixResult]:
        """Apply selected patches to the pipeline definition.

        Patches are applied in order. If a patch becomes invalid after a prior
        patch changed the graph, it is skipped.

        Returns:
            Tuple of (modified_nodes, modified_edges, result).
        """
        nodes = copy.deepcopy(pipeline_nodes)
        edges = copy.deepcopy(pipeline_edges)
        result = AutofixResult()

        if all_patches is None:
            return nodes, edges, result

        patch_map = {p.patch_id: p for p in all_patches}

        for pid in patch_ids:
            patch = patch_map.get(pid)
            if patch is None:
                result.skipped.append({"patch_id": pid, "reason": "Patch not found"})
                continue

            try:
                nodes, edges = self._apply_single_patch(patch, nodes, edges)
                result.applied.append(pid)
            except _PatchInvalidError as exc:
                result.skipped.append({"patch_id": pid, "reason": str(exc)})

        return nodes, edges, result

    # ── Fix Generators ───────────────────────────────────────────

    def _fix_stale_output_handle(
        self, msg: str, node_map: dict, edges: list[dict],
    ) -> list[AutofixPatch]:
        """Fix edges referencing non-existent output ports by mapping aliases."""
        match = re.search(
            r"Edge from '([^']+)' references non-existent output port '([^']+)'",
            msg,
        )
        if not match:
            return []

        node_label = match.group(1)
        stale_port = match.group(2)

        # Find the node by label
        node = self._find_node_by_label(node_label, node_map)
        if not node:
            return []

        block_type = node.get("data", {}).get("type", "")
        if not block_type:
            return []

        # Check if the stale port is an alias for a current port
        canonical = self._registry.resolve_output_handle(block_type, stale_port)
        if canonical == stale_port:
            # Not an alias — check if a similarly-named port exists
            schema = self._registry.get(block_type)
            if schema is None:
                return []
            current_outputs = {p.id for p in schema.outputs}
            if stale_port not in current_outputs and len(current_outputs) == 1:
                # Single output port — likely renamed
                canonical = next(iter(current_outputs))
            else:
                return []

        # Find edges that use this stale handle
        patches: list[AutofixPatch] = []
        for edge in edges:
            if edge.get("source") == node["id"] and edge.get("sourceHandle") == stale_port:
                patches.append(AutofixPatch(
                    patch_id=str(uuid.uuid4()),
                    node_id=node["id"],
                    field="sourceHandle",
                    action="rename",
                    old_value=stale_port,
                    new_value=canonical,
                    reason=f"Output port '{stale_port}' was renamed to '{canonical}'",
                    confidence="high",
                    edge_id=edge.get("id"),
                ))

        return patches

    def _fix_stale_input_handle(
        self, msg: str, node_map: dict, edges: list[dict],
    ) -> list[AutofixPatch]:
        """Fix edges referencing non-existent input ports."""
        match = re.search(
            r"Edge to '([^']+)' references non-existent input port '([^']+)'",
            msg,
        )
        if not match:
            return []

        node_label = match.group(1)
        stale_port = match.group(2)

        node = self._find_node_by_label(node_label, node_map)
        if not node:
            return []

        block_type = node.get("data", {}).get("type", "")
        if not block_type:
            return []

        schema = self._registry.get(block_type)
        if schema is None:
            return []

        # Check input port aliases
        canonical = None
        for inp in schema.inputs:
            if stale_port in inp.aliases:
                canonical = inp.id
                break

        if canonical is None:
            current_inputs = {p.id for p in schema.inputs}
            if stale_port not in current_inputs and len(current_inputs) == 1:
                canonical = next(iter(current_inputs))
            else:
                return []

        patches: list[AutofixPatch] = []
        for edge in edges:
            if edge.get("target") == node["id"] and edge.get("targetHandle") == stale_port:
                patches.append(AutofixPatch(
                    patch_id=str(uuid.uuid4()),
                    node_id=node["id"],
                    field="targetHandle",
                    action="rename",
                    old_value=stale_port,
                    new_value=canonical,
                    reason=f"Input port '{stale_port}' was renamed to '{canonical}'",
                    confidence="high",
                    edge_id=edge.get("id"),
                ))

        return patches

    def _fix_outdated_ports(
        self, msg: str, node_map: dict, edges: list[dict],
    ) -> list[AutofixPatch]:
        """Fix edges connected to removed ports when block version changed."""
        match = re.search(
            r"Block '([^']+)' has outdated ports \(([^)]+)\)",
            msg,
        )
        if not match:
            return []

        node_label = match.group(1)
        removed_ports_str = match.group(2)
        removed_ports = {p.strip() for p in removed_ports_str.split(",")}

        node = self._find_node_by_label(node_label, node_map)
        if not node:
            return []

        block_type = node.get("data", {}).get("type", "")
        if not block_type:
            return []

        schema = self._registry.get(block_type)
        if schema is None:
            return []

        patches: list[AutofixPatch] = []
        # For each removed port, check if it's an alias for a current port
        output_alias_map = self._registry.get_output_alias_map(block_type)
        input_alias_map = {}
        for inp in schema.inputs:
            for alias in inp.aliases:
                input_alias_map[alias] = inp.id

        for port_id in removed_ports:
            canonical = output_alias_map.get(port_id) or input_alias_map.get(port_id)
            if not canonical:
                continue

            for edge in edges:
                if edge.get("source") == node["id"] and edge.get("sourceHandle") == port_id:
                    patches.append(AutofixPatch(
                        patch_id=str(uuid.uuid4()),
                        node_id=node["id"],
                        field="sourceHandle",
                        action="rename",
                        old_value=port_id,
                        new_value=canonical,
                        reason=f"Port '{port_id}' was renamed to '{canonical}' in the new version",
                        confidence="high",
                        edge_id=edge.get("id"),
                    ))
                if edge.get("target") == node["id"] and edge.get("targetHandle") == port_id:
                    patches.append(AutofixPatch(
                        patch_id=str(uuid.uuid4()),
                        node_id=node["id"],
                        field="targetHandle",
                        action="rename",
                        old_value=port_id,
                        new_value=canonical,
                        reason=f"Port '{port_id}' was renamed to '{canonical}' in the new version",
                        confidence="high",
                        edge_id=edge.get("id"),
                    ))

        return patches

    def _fix_missing_config(
        self, msg: str, node_map: dict,
    ) -> list[AutofixPatch]:
        """Fix missing required config fields that have schema defaults."""
        match = re.search(
            r"Block '([^']+)': '([^']+)' is required but empty",
            msg,
        )
        if not match:
            return []

        node_label = match.group(1)
        config_key = match.group(2)

        node = self._find_node_by_label(node_label, node_map)
        if not node:
            return []

        block_type = node.get("data", {}).get("type", "")
        if not block_type:
            return []

        # Check if the schema provides a default for this field
        config_schema = self._registry.get_block_config_schema(block_type)
        if not config_schema:
            return []

        field_spec = config_schema.get(config_key)
        if not isinstance(field_spec, dict):
            return []

        default_value = field_spec.get("default")
        if default_value is None:
            return []

        current_value = node.get("data", {}).get("config", {}).get(config_key)

        return [AutofixPatch(
            patch_id=str(uuid.uuid4()),
            node_id=node["id"],
            field=f"config.{config_key}",
            action="set",
            old_value=current_value,
            new_value=default_value,
            reason=f"Apply schema default '{default_value}' for required field '{config_key}'",
            confidence="high",
        )]

    def _fix_incompatible_connection(
        self, msg: str, node_map: dict, edges: list[dict],
    ) -> list[AutofixPatch]:
        """Suggest inserting a converter block for incompatible connections.

        Searches the registry for a block whose input accepts the source
        data_type and whose output is compatible with the target data_type.
        Proposes an ``insert_converter`` patch that removes the old edge,
        creates a converter node, and wires source→converter→target.

        Falls back to a ``delete`` edge patch only if no converter exists.
        """
        match = re.search(
            r"Incompatible connection: Cannot connect (\w+) \(([^)]+)\) to (\w+) \(([^)]+)\)",
            msg,
        )
        if not match:
            match = re.search(
                r"Incompatible: (\w+) \(port '([^']+)'\) cannot connect to (\w+) \(port '([^']+)'\)",
                msg,
            )
        if not match:
            return []

        src_data_type = match.group(1).lower()
        src_label_or_port = match.group(2)
        tgt_data_type = match.group(3).lower()
        tgt_label_or_port = match.group(4)

        src_node = self._find_node_by_label(src_label_or_port, node_map)
        tgt_node = self._find_node_by_label(tgt_label_or_port, node_map)

        if not src_node or not tgt_node:
            return []

        # Find the offending edge (need its ID and handles)
        target_edge = None
        for edge in edges:
            if edge.get("source") == src_node["id"] and edge.get("target") == tgt_node["id"]:
                target_edge = edge
                break

        if not target_edge:
            return []

        # ── Search registry for a converter block ──
        converter = self._find_converter_block(src_data_type, tgt_data_type)

        if converter:
            converter_type, in_port_id, out_port_id = converter
            converter_schema = self._registry.get(converter_type)
            converter_label = converter_schema.label if converter_schema else converter_type

            # Compute position: midpoint between source and target nodes
            src_pos = src_node.get("position", {})
            tgt_pos = tgt_node.get("position", {})
            mid_x = (src_pos.get("x", 0) + tgt_pos.get("x", 400)) / 2
            mid_y = (src_pos.get("y", 0) + tgt_pos.get("y", 0)) / 2

            return [AutofixPatch(
                patch_id=str(uuid.uuid4()),
                node_id=tgt_node["id"],
                field="converter",
                action="insert_converter",
                old_value=target_edge.get("id"),
                new_value={
                    "converter_block_type": converter_type,
                    "converter_label": converter_label,
                    "converter_category": converter_schema.category if converter_schema else "data",
                    "position": {"x": mid_x, "y": mid_y},
                    "source_node_id": src_node["id"],
                    "source_handle": target_edge.get("sourceHandle", ""),
                    "target_node_id": tgt_node["id"],
                    "target_handle": target_edge.get("targetHandle", ""),
                    "converter_in_port": in_port_id,
                    "converter_out_port": out_port_id,
                },
                reason=(
                    f"Insert '{converter_label}' to convert "
                    f"{src_data_type} -> {tgt_data_type}"
                ),
                confidence="medium",
                edge_id=target_edge.get("id"),
                source_id=src_node["id"],
                target_id=tgt_node["id"],
            )]

        # Fallback: no converter found → propose edge removal
        return [AutofixPatch(
            patch_id=str(uuid.uuid4()),
            node_id=tgt_node["id"],
            field="edge",
            action="delete",
            old_value=target_edge.get("id"),
            new_value=None,
            reason=(
                f"Remove incompatible connection: {src_data_type} cannot connect "
                f"to {tgt_data_type} (no converter block available)"
            ),
            confidence="medium",
            edge_id=target_edge.get("id"),
            source_id=src_node["id"],
            target_id=tgt_node["id"],
        )]

    def _find_converter_block(
        self, src_data_type: str, tgt_data_type: str,
    ) -> tuple[str, str, str] | None:
        """Search the registry for a block that converts src_data_type to tgt_data_type.

        A converter is a block with at least one input port compatible with
        ``src_data_type`` and at least one output port compatible with
        ``tgt_data_type``.

        Selection criteria (in order of preference):
        1. Blocks tagged with 'adapter' or 'conversion' (purpose-built converters)
        2. Blocks with the fewest total ports (simpler = more likely a pure converter)
        3. Blocks that are not deprecated

        Returns ``(block_type, input_port_id, output_port_id)`` or ``None``.
        """
        candidates: list[tuple[int, str, str, str]] = []

        for schema in self._registry.list_all():
            if schema.deprecated:
                continue
            if schema.maturity == "broken":
                continue

            # Find a matching input port (accepts src_data_type)
            matching_in = None
            for inp in schema.inputs:
                if self._registry.is_port_compatible(src_data_type, inp.data_type):
                    matching_in = inp
                    break

            if matching_in is None:
                continue

            # Find a matching output port (produces tgt_data_type)
            matching_out = None
            for out in schema.outputs:
                if self._registry.is_port_compatible(out.data_type, tgt_data_type):
                    matching_out = out
                    break

            if matching_out is None:
                continue

            # Skip blocks where input and output types are the same (pass-through, not converter)
            if matching_in.data_type == matching_out.data_type and matching_in.data_type != "any":
                continue

            # Score: prefer purpose-built converters, then fewer total ports
            tags = set(schema.tags)
            is_adapter = bool(tags & {"adapter", "conversion", "converter", "bridge"})
            total_ports = len(schema.inputs) + len(schema.outputs) + len(schema.side_inputs)
            # Lower score = better. Adapters get -1000 bonus.
            score = total_ports + (0 if is_adapter else 1000)

            candidates.append((score, schema.block_type, matching_in.id, matching_out.id))

        if not candidates:
            return None

        candidates.sort(key=lambda c: c[0])
        _, block_type, in_port, out_port = candidates[0]
        return (block_type, in_port, out_port)

    def _fix_missing_required_input(
        self, msg: str, node_map: dict,
        all_nodes: list[dict], edges: list[dict],
    ) -> list[AutofixPatch]:
        """Suggest connecting an existing upstream block for missing required inputs."""
        match = re.search(
            r"Block '([^']+)' is missing required input: (.+)",
            msg,
        )
        if not match:
            # Also match the planner-style format
            match = re.search(
                r"Required input port '([^']+)' on block '([^']+)' is not connected",
                msg,
            )
            if match:
                port_label = match.group(1)
                node_label = match.group(2)
            else:
                return []
        else:
            node_label = match.group(1)
            port_label = match.group(2)

        node = self._find_node_by_label(node_label, node_map)
        if not node:
            return []

        block_type = node.get("data", {}).get("type", "")
        if not block_type:
            return []

        schema = self._registry.get(block_type)
        if schema is None:
            return []

        # Find the target port's data type
        target_port = None
        for inp in schema.inputs:
            if inp.id == port_label or inp.label == port_label:
                target_port = inp
                break

        if target_port is None:
            return []

        target_dt = target_port.data_type

        # Find an existing upstream node that produces a compatible output
        connected_sources = {
            e.get("source") for e in edges if e.get("target") == node["id"]
        }
        best_source = None
        best_port_id = None

        for candidate in all_nodes:
            if candidate["id"] == node["id"]:
                continue
            if candidate["id"] in connected_sources:
                continue
            if candidate.get("type") in ("groupNode", "stickyNote"):
                continue

            cand_type = candidate.get("data", {}).get("type", "")
            cand_schema = self._registry.get(cand_type) if cand_type else None
            if cand_schema is None:
                continue

            for out in cand_schema.outputs:
                if self._registry.is_port_compatible(out.data_type, target_dt):
                    best_source = candidate
                    best_port_id = out.id
                    break
            if best_source:
                break

        if not best_source or not best_port_id:
            return []

        src_label = best_source.get("data", {}).get("label", best_source["id"])
        return [AutofixPatch(
            patch_id=str(uuid.uuid4()),
            node_id=node["id"],
            field="edge",
            action="add_edge",
            old_value=None,
            new_value={
                "source": best_source["id"],
                "sourceHandle": best_port_id,
                "target": node["id"],
                "targetHandle": target_port.id,
            },
            reason=f"Connect '{src_label}' -> '{node_label}' ({target_port.id})",
            confidence="medium",
            source_id=best_source["id"],
            target_id=node["id"],
        )]

    # ── Patch Application ────────────────────────────────────────

    def _apply_single_patch(
        self,
        patch: AutofixPatch,
        nodes: list[dict],
        edges: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """Apply a single patch. Raises _PatchInvalidError if the patch no longer applies."""

        if patch.action == "rename" and patch.field == "sourceHandle":
            return self._apply_rename_handle(patch, nodes, edges, "source", "sourceHandle")

        if patch.action == "rename" and patch.field == "targetHandle":
            return self._apply_rename_handle(patch, nodes, edges, "target", "targetHandle")

        if patch.action == "set" and patch.field.startswith("config."):
            config_key = patch.field[len("config."):]
            node = self._find_node_by_id(patch.node_id, nodes)
            if not node:
                raise _PatchInvalidError(f"Node '{patch.node_id}' no longer exists")
            data = node.setdefault("data", {})
            config = data.setdefault("config", {})
            config[config_key] = patch.new_value
            return nodes, edges

        if patch.action == "delete" and patch.field == "edge":
            edge_id = patch.old_value
            original_len = len(edges)
            edges = [e for e in edges if e.get("id") != edge_id]
            if len(edges) == original_len:
                raise _PatchInvalidError(f"Edge '{edge_id}' no longer exists")
            return nodes, edges

        if patch.action == "add_edge":
            edge_spec = patch.new_value
            if not isinstance(edge_spec, dict):
                raise _PatchInvalidError("Invalid edge specification")
            # Check that the source and target nodes still exist
            node_ids = {n["id"] for n in nodes}
            if edge_spec["source"] not in node_ids:
                raise _PatchInvalidError(f"Source node '{edge_spec['source']}' no longer exists")
            if edge_spec["target"] not in node_ids:
                raise _PatchInvalidError(f"Target node '{edge_spec['target']}' no longer exists")
            # Check for duplicate edge
            for e in edges:
                if (e.get("source") == edge_spec["source"]
                        and e.get("target") == edge_spec["target"]
                        and e.get("sourceHandle") == edge_spec.get("sourceHandle")
                        and e.get("targetHandle") == edge_spec.get("targetHandle")):
                    raise _PatchInvalidError("Edge already exists")
            new_edge = {
                "id": f"autofix-{uuid.uuid4().hex[:8]}",
                **edge_spec,
            }
            edges.append(new_edge)
            return nodes, edges

        if patch.action == "set" and patch.field == "block_type":
            node = self._find_node_by_id(patch.node_id, nodes)
            if not node:
                raise _PatchInvalidError(f"Node '{patch.node_id}' no longer exists")
            node.setdefault("data", {})["type"] = patch.new_value
            return nodes, edges

        if patch.action == "insert_converter" and patch.field == "converter":
            return self._apply_insert_converter(patch, nodes, edges)

        raise _PatchInvalidError(f"Unknown patch action: {patch.action}/{patch.field}")

    def _apply_insert_converter(
        self,
        patch: AutofixPatch,
        nodes: list[dict],
        edges: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """Apply an insert_converter patch: remove old edge, add converter node, wire it in."""
        spec = patch.new_value
        if not isinstance(spec, dict):
            raise _PatchInvalidError("Invalid converter specification")

        old_edge_id = patch.old_value
        converter_type = spec["converter_block_type"]
        position = spec.get("position", {"x": 0, "y": 0})
        src_node_id = spec["source_node_id"]
        src_handle = spec["source_handle"]
        tgt_node_id = spec["target_node_id"]
        tgt_handle = spec["target_handle"]
        conv_in_port = spec["converter_in_port"]
        conv_out_port = spec["converter_out_port"]

        # Validate source and target nodes still exist
        node_ids = {n["id"] for n in nodes}
        if src_node_id not in node_ids:
            raise _PatchInvalidError(f"Source node '{src_node_id}' no longer exists")
        if tgt_node_id not in node_ids:
            raise _PatchInvalidError(f"Target node '{tgt_node_id}' no longer exists")

        # Remove the old incompatible edge
        original_len = len(edges)
        edges = [e for e in edges if e.get("id") != old_edge_id]
        if len(edges) == original_len:
            raise _PatchInvalidError(f"Edge '{old_edge_id}' no longer exists")

        # Create the converter node
        converter_node_id = f"autofix-{uuid.uuid4().hex[:8]}"
        schema = self._registry.get(converter_type)
        converter_node = {
            "id": converter_node_id,
            "type": "default",
            "position": position,
            "data": {
                "type": converter_type,
                "label": spec.get("converter_label", converter_type),
                "category": spec.get("converter_category", "data"),
                "icon": schema.icon if schema else "",
                "accent": schema.accent if schema else "",
                "config": {},
                "status": "idle",
                "progress": 0,
            },
        }
        nodes.append(converter_node)

        # Wire: source → converter
        edges.append({
            "id": f"autofix-{uuid.uuid4().hex[:8]}",
            "source": src_node_id,
            "sourceHandle": src_handle,
            "target": converter_node_id,
            "targetHandle": conv_in_port,
        })

        # Wire: converter → target
        edges.append({
            "id": f"autofix-{uuid.uuid4().hex[:8]}",
            "source": converter_node_id,
            "sourceHandle": conv_out_port,
            "target": tgt_node_id,
            "targetHandle": tgt_handle,
        })

        return nodes, edges

    def _apply_rename_handle(
        self,
        patch: AutofixPatch,
        nodes: list[dict],
        edges: list[dict],
        node_key: str,
        handle_key: str,
    ) -> tuple[list[dict], list[dict]]:
        """Rename an edge handle (sourceHandle or targetHandle)."""
        found = False
        for edge in edges:
            if patch.edge_id and edge.get("id") == patch.edge_id:
                if edge.get(handle_key) != patch.old_value:
                    raise _PatchInvalidError(
                        f"Edge '{patch.edge_id}' handle is '{edge.get(handle_key)}', "
                        f"expected '{patch.old_value}'"
                    )
                edge[handle_key] = patch.new_value
                found = True
                break
            elif (not patch.edge_id
                  and edge.get(node_key) == patch.node_id
                  and edge.get(handle_key) == patch.old_value):
                edge[handle_key] = patch.new_value
                found = True
                break

        if not found:
            raise _PatchInvalidError(
                f"Edge with {handle_key}='{patch.old_value}' on node '{patch.node_id}' not found"
            )

        return nodes, edges

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _find_node_by_label(label: str, node_map: dict) -> dict | None:
        """Find a node by its display label or by its ID."""
        for node in node_map.values():
            if node.get("data", {}).get("label") == label:
                return node
        # Fall back to matching by ID directly
        return node_map.get(label)

    @staticmethod
    def _find_node_by_id(node_id: str, nodes: list[dict]) -> dict | None:
        for node in nodes:
            if node["id"] == node_id:
                return node
        return None


class _PatchInvalidError(Exception):
    """Raised when a patch can no longer be applied to the current graph state."""
