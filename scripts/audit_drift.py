#!/usr/bin/env python3
"""
audit_drift.py — Scans the repo for drift between claims and reality.

Checks:
1. Block counts: blocks/ directory vs README claims
2. Block category counts
3. Duplicate compatibility maps (backend vs frontend)
4. Router count
5. Model count
6. Script count

Outputs to docs/REPO_FACTS.json. Exit code 1 if drift found.
"""

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
BLOCKS_DIR = REPO_ROOT / "blocks"
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
DOCS_DIR = REPO_ROOT / "docs"

drift_found = False
facts: dict = {}
drift_details: list[str] = []


def scan_blocks() -> dict:
    """Count blocks per category."""
    categories: dict[str, list[str]] = {}
    total = 0
    if not BLOCKS_DIR.exists():
        return {"total": 0, "categories": {}}
    for cat_dir in sorted(BLOCKS_DIR.iterdir()):
        if not cat_dir.is_dir() or cat_dir.name.startswith((".", "_")):
            continue
        blocks = []
        for block_dir in sorted(cat_dir.iterdir()):
            if not block_dir.is_dir() or block_dir.name.startswith((".", "_")):
                continue
            run_py = block_dir / "run.py"
            block_yaml = block_dir / "block.yaml"
            if run_py.exists():
                blocks.append({
                    "name": block_dir.name,
                    "has_yaml": block_yaml.exists(),
                })
                total += 1
        categories[cat_dir.name] = blocks
    return {
        "total": total,
        "categories": {k: len(v) for k, v in categories.items()},
        "blocks_without_yaml": [
            f"{cat}/{b['name']}"
            for cat, blocks in categories.items()
            for b in blocks
            if not b["has_yaml"]
        ],
    }


def check_readme_claims(block_facts: dict) -> None:
    """Check README claims against actual block counts."""
    global drift_found
    readme = REPO_ROOT / "README.md"
    if not readme.exists():
        return

    content = readme.read_text()

    # Look for block count claims like "118+ ML Blocks" or "132 blocks"
    count_match = re.search(r"(\d+)\+?\s*(?:ML\s+)?[Bb]locks", content)
    if count_match:
        claimed = int(count_match.group(1))
        actual = block_facts["total"]
        facts["readme_claimed_blocks"] = claimed
        if abs(claimed - actual) > 5:
            drift_found = True
            drift_details.append(
                f"README claims {claimed} blocks but found {actual} "
                f"(delta: {actual - claimed})"
            )

    # Look for category count claims like "9 categories"
    cat_match = re.search(r"(\d+)\s+categor", content)
    if cat_match:
        claimed_cats = int(cat_match.group(1))
        actual_cats = len(block_facts["categories"])
        facts["readme_claimed_categories"] = claimed_cats
        if claimed_cats != actual_cats:
            drift_found = True
            drift_details.append(
                f"README claims {claimed_cats} categories but found {actual_cats}"
            )


def scan_compatibility_maps() -> dict:
    """Extract and compare compatibility maps from frontend and backend."""
    global drift_found
    result = {"frontend": {}, "backend": {}, "drift": []}

    # Frontend COMPAT from block-registry-types.ts
    fe_file = FRONTEND_DIR / "src" / "lib" / "block-registry-types.ts"
    if fe_file.exists():
        fe_content = fe_file.read_text()
        # Parse the COMPAT record
        compat_match = re.search(
            r"const COMPAT:\s*Record<string,\s*Set<string>>\s*=\s*\{(.*?)\}",
            fe_content,
            re.DOTALL,
        )
        if compat_match:
            block = compat_match.group(1)
            for line in block.split("\n"):
                m = re.match(
                    r"\s*(\w+):\s*new Set\(\[([^\]]*)\]\)",
                    line,
                )
                if m:
                    src = m.group(1)
                    targets = [
                        t.strip().strip("'\"")
                        for t in m.group(2).split(",")
                        if t.strip()
                    ]
                    result["frontend"][src] = sorted(targets)

    # Backend COMPAT from validator.py
    # Supports both formats:
    #   Old: set of tuples  {("src", "tgt"), ...}
    #   New: dict of sets   {"src": {"tgt1", "tgt2"}, ...}
    be_file = BACKEND_DIR / "engine" / "validator.py"
    if be_file.exists():
        be_content = be_file.read_text()
        compat_match = re.search(
            r"COMPAT[^=]*=\s*\{(.*?)\n\}", be_content, re.DOTALL
        )
        if compat_match:
            block = compat_match.group(1)
            be_map: dict[str, set[str]] = {}
            # Try new dict-of-sets format: "key": {"val1", "val2"}
            for m in re.finditer(
                r'"(\w+)":\s*\{([^}]*)\}', block
            ):
                src = m.group(1)
                targets = {
                    t.strip().strip('"').strip("'")
                    for t in m.group(2).split(",")
                    if t.strip().strip('"').strip("'")
                }
                be_map[src] = targets
            # Fallback: old tuple-set format
            if not be_map:
                for m in re.finditer(r'\("(\w+)",\s*"(\w+)"\)', block):
                    src, tgt = m.group(1), m.group(2)
                    be_map.setdefault(src, set()).add(tgt)
            result["backend"] = {k: sorted(v) for k, v in sorted(be_map.items())}

    # Check for drift
    all_types = set(result["frontend"].keys()) | set(result["backend"].keys())
    for t in sorted(all_types):
        fe_set = set(result["frontend"].get(t, []))
        be_set = set(result["backend"].get(t, []))
        if fe_set != be_set:
            only_fe = fe_set - be_set
            only_be = be_set - fe_set
            detail = f"Port compat drift for '{t}':"
            if only_fe:
                detail += f" frontend-only targets: {sorted(only_fe)}"
            if only_be:
                detail += f" backend-only targets: {sorted(only_be)}"
            result["drift"].append(detail)
            drift_found = True
            drift_details.append(detail)

    # Check aliases
    fe_aliases = {}
    if fe_file.exists():
        fe_content = fe_file.read_text()
        alias_match = re.search(
            r"const PORT_TYPE_ALIASES:\s*Record<string,\s*string>\s*=\s*\{(.*?)\}",
            fe_content,
            re.DOTALL,
        )
        if alias_match:
            for m in re.finditer(r"(\w+):\s*'(\w+)'", alias_match.group(1)):
                fe_aliases[m.group(1)] = m.group(2)

    be_aliases = {}
    if be_file.exists():
        be_content = be_file.read_text()
        alias_match = re.search(
            r"_PORT_TYPE_ALIASES.*?=\s*\{(.*?)\}", be_content, re.DOTALL
        )
        if alias_match:
            for m in re.finditer(r'"(\w+)":\s*"(\w+)"', alias_match.group(1)):
                be_aliases[m.group(1)] = m.group(2)

    result["frontend_aliases"] = fe_aliases
    result["backend_aliases"] = be_aliases

    if fe_aliases != be_aliases:
        only_fe = {k: v for k, v in fe_aliases.items() if k not in be_aliases or be_aliases[k] != v}
        only_be = {k: v for k, v in be_aliases.items() if k not in fe_aliases or fe_aliases[k] != v}
        detail = "Port type alias drift:"
        if only_fe:
            detail += f" frontend-only: {only_fe}"
        if only_be:
            detail += f" backend-only: {only_be}"
        result["drift"].append(detail)
        drift_found = True
        drift_details.append(detail)

    return result


def scan_routers() -> list[str]:
    """List backend routers."""
    routers_dir = BACKEND_DIR / "routers"
    if not routers_dir.exists():
        return []
    return sorted(
        f.stem
        for f in routers_dir.iterdir()
        if f.suffix == ".py" and f.stem != "__init__"
    )


def scan_models() -> list[str]:
    """List backend SQLAlchemy models."""
    models_dir = BACKEND_DIR / "models"
    if not models_dir.exists():
        return []
    return sorted(
        f.stem
        for f in models_dir.iterdir()
        if f.suffix == ".py" and f.stem != "__init__"
    )


def scan_scripts() -> list[str]:
    """List scripts."""
    scripts_dir = REPO_ROOT / "scripts"
    if not scripts_dir.exists():
        return []
    return sorted(
        f.name
        for f in scripts_dir.iterdir()
        if f.is_file() and not f.name.startswith(".")
    )


def main() -> int:
    global drift_found

    # 1. Scan blocks
    block_facts = scan_blocks()
    facts["blocks"] = block_facts

    # 2. Check README claims
    check_readme_claims(block_facts)

    # 3. Scan compatibility maps
    compat_facts = scan_compatibility_maps()
    facts["compatibility_maps"] = compat_facts

    # 4. Scan routers
    facts["routers"] = scan_routers()
    facts["router_count"] = len(facts["routers"])

    # 5. Scan models
    facts["models"] = scan_models()
    facts["model_count"] = len(facts["models"])

    # 6. Scan scripts
    facts["scripts"] = scan_scripts()
    facts["script_count"] = len(facts["scripts"])

    # 7. Drift summary
    facts["drift_found"] = drift_found
    facts["drift_details"] = drift_details

    # Write output
    output_path = DOCS_DIR / "REPO_FACTS.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(facts, f, indent=2, sort_keys=False)

    print(f"Wrote {output_path}")
    if drift_found:
        print(f"\nDRIFT DETECTED ({len(drift_details)} issues):")
        for d in drift_details:
            print(f"  - {d}")
        return 1
    else:
        print("\nNo drift detected.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
