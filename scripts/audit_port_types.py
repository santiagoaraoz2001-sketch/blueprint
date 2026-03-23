#!/usr/bin/env python3
"""Audit all block.yaml files for port naming/typing inconsistencies.

Checks:
  A) Port name vs type mismatch — flag when port id suggests one type
     but data_type says another (skips data_type: any since those are
     intentionally generic pass-through ports).
  B) Duplicate port IDs — two inputs or two outputs with the same id.
  C) Missing data_type — any port without a data_type field.
"""

import os
import sys
import yaml
from pathlib import Path

# Port name -> expected data_type mappings
NAME_TYPE_RULES = {
    # Exact matches
    "model": "model",
    "dataset": "dataset",
    "data": "dataset",
    "text": "text",
    "response": "text",
    "prompt": "text",
    "metrics": "metrics",
    "config": "config",
    "artifact": "artifact",
    "report": "artifact",
    # Prefix matches handled separately
}

PREFIX_RULES = {
    "model_": "model",
    "embedding": "embedding",
}


def get_expected_type(port_id):
    """Return expected data_type for a port id, or None if no rule matches."""
    # Check exact matches first
    if port_id in NAME_TYPE_RULES:
        return NAME_TYPE_RULES[port_id]
    # Check prefix matches
    for prefix, expected_type in PREFIX_RULES.items():
        if port_id.startswith(prefix):
            return expected_type
    return None


def audit_block(yaml_path):
    """Audit a single block.yaml file. Returns list of issues."""
    issues = []

    with open(yaml_path, 'r') as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            issues.append(f"  YAML PARSE ERROR: {e}")
            return issues

    if not data:
        return issues

    for direction in ['inputs', 'outputs']:
        ports = data.get(direction, [])
        if not ports:
            continue

        seen_ids = {}
        for port in ports:
            port_id = port.get('id')
            data_type = port.get('data_type')
            label = port.get('label', '')

            # Check: missing port id
            if not port_id:
                issues.append(f"  MISSING_ID: {direction} port (label={label!r}) has no id")
                continue

            # Check B: Duplicate port IDs (always checked, regardless of data_type)
            if port_id in seen_ids:
                issues.append(f"  DUPLICATE_ID: {direction}.{port_id} appears multiple times")
            seen_ids[port_id] = True

            # Check C: Missing data_type
            if not data_type:
                issues.append(f"  MISSING_TYPE: {direction}.{port_id} has no data_type")
                continue

            # Check A: Name vs type mismatch
            # Skip for 'any' type — these ports are intentionally generic
            if data_type == 'any':
                continue
            expected = get_expected_type(port_id)
            if expected and data_type != expected:
                issues.append(
                    f"  MISMATCH: {direction}.{port_id} has data_type={data_type}, "
                    f"expected={expected} (label: {label})"
                )

    return issues


def main():
    blocks_dir = Path(__file__).parent.parent / "blocks"

    all_issues = {}
    total_blocks = 0
    total_issues = 0

    for yaml_path in sorted(blocks_dir.rglob("block.yaml")):
        total_blocks += 1
        issues = audit_block(yaml_path)
        if issues:
            rel = os.path.relpath(yaml_path)
            all_issues[rel] = issues
            total_issues += len(issues)

    print(f"Audited {total_blocks} block.yaml files\n")

    if all_issues:
        print(f"Found {total_issues} issues in {len(all_issues)} files:\n")
        for path, issues in sorted(all_issues.items()):
            print(f"{path}:")
            for issue in issues:
                print(issue)
            print()
        sys.exit(1)
    else:
        print("No issues found!")
        sys.exit(0)


if __name__ == "__main__":
    main()
