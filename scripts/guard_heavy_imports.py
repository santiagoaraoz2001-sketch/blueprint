#!/usr/bin/env python3
"""Guard all heavy dependency imports with try/except BlockDependencyError.

Scans all blocks/*/run.py files and:
1. Identifies try/except ImportError blocks that don't use BlockDependencyError
2. Replaces the except handler with BlockDependencyError pattern
3. Reports which blocks were fixed
"""

import ast
import os
import re
import sys

HEAVY_DEPS = {
    "torch", "transformers", "mlx", "datasets", "numpy", "pandas",
    "scipy", "sklearn", "sentence_transformers", "peft", "trl",
    "wandb", "nbformat", "huggingface_hub",
}

INSTALL_HINTS = {
    "torch": "pip install torch",
    "transformers": "pip install transformers",
    "mlx": "pip install mlx mlx-lm",
    "datasets": "pip install datasets",
    "numpy": "pip install numpy",
    "pandas": "pip install pandas",
    "scipy": "pip install scipy",
    "sklearn": "pip install scikit-learn",
    "sentence_transformers": "pip install sentence-transformers",
    "peft": "pip install peft",
    "trl": "pip install trl",
    "wandb": "pip install wandb",
    "nbformat": "pip install nbformat",
    "huggingface_hub": "pip install huggingface_hub",
}


def get_top_module(name):
    return name.split(".")[0] if name else ""


def is_heavy(name):
    return get_top_module(name) in HEAVY_DEPS


def get_heavy_deps_in_try(try_node):
    """Extract heavy dependency top-module names from a try block's body."""
    deps = set()
    for node in ast.walk(ast.Module(body=try_node.body, type_ignores=[])):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = get_top_module(alias.name)
                if top in HEAVY_DEPS:
                    deps.add(top)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = get_top_module(node.module)
                if top in HEAVY_DEPS:
                    deps.add(top)
    return deps


def build_install_hint(deps):
    """Build a combined install hint for a set of dependencies."""
    packages = []
    for dep in sorted(deps):
        hint = INSTALL_HINTS.get(dep, f"pip install {dep}")
        pkg = hint.replace("pip install ", "")
        packages.extend(pkg.split())
    return "pip install " + " ".join(sorted(set(packages)))


def uses_block_dependency_error(handler_body):
    """Check if an except handler already uses BlockDependencyError."""
    for node in ast.walk(ast.Module(body=handler_body, type_ignores=[])):
        if isinstance(node, ast.Name) and node.id == "BlockDependencyError":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "BlockDependencyError":
            return True
    return False


def get_except_handler_range(source_lines, try_node):
    """Get the line range (0-indexed) of the except ImportError handler."""
    for handler in try_node.handlers:
        if handler.type is None:
            continue
        # Check if it's ImportError
        handler_type = None
        if isinstance(handler.type, ast.Name):
            handler_type = handler.type.id
        elif isinstance(handler.type, ast.Attribute):
            handler_type = handler.type.attr

        if handler_type == "ImportError":
            # Handler starts at handler.lineno (1-indexed)
            start = handler.lineno - 1  # 0-indexed
            # End is the last line of the handler body
            end = max(n.end_lineno for n in handler.body if hasattr(n, 'end_lineno'))
            return start, end  # 0-indexed, inclusive
    return None, None


def make_bde_handler(deps, indent, has_as_e=True):
    """Create the BlockDependencyError except handler text."""
    install_hint = build_install_hint(deps)
    e_var = "e" if has_as_e else "e"

    lines = [
        f"{indent}except ImportError as {e_var}:",
        f"{indent}    from backend.block_sdk.exceptions import BlockDependencyError",
        f"{indent}    missing = str({e_var}).split(\"'\")[-2] if \"'\" in str({e_var}) else str({e_var})",
        f"{indent}    raise BlockDependencyError(",
        f"{indent}        missing,",
        f"{indent}        f\"Required library not installed: {{{e_var}}}\",",
        f"{indent}        install_hint=\"{install_hint}\",",
        f"{indent}    )",
    ]
    return lines


def process_file(filepath):
    """Process a single run.py file and return (modified, changes_made)."""
    with open(filepath) as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source, []

    source_lines = source.splitlines()
    changes = []
    replacements = []  # (start_line_0idx, end_line_0idx, new_lines)

    # Walk all nodes to find try/except blocks with heavy imports
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue

        deps = get_heavy_deps_in_try(node)
        if not deps:
            continue

        # Check handlers
        for handler in node.handlers:
            if handler.type is None:
                continue

            handler_type = None
            if isinstance(handler.type, ast.Name):
                handler_type = handler.type.id
            elif isinstance(handler.type, ast.Attribute):
                handler_type = handler.type.attr

            if handler_type != "ImportError":
                continue

            # Already uses BlockDependencyError?
            if uses_block_dependency_error(handler.body):
                continue

            # Get the except line and handler body range
            except_line = handler.lineno - 1  # 0-indexed
            handler_end = max(
                getattr(n, 'end_lineno', handler.lineno)
                for n in handler.body
            )  # 1-indexed

            # Determine indent from the except line
            except_text = source_lines[except_line]
            indent = " " * (len(except_text) - len(except_text.lstrip()))

            has_as_e = handler.name is not None
            new_lines = make_bde_handler(deps, indent, has_as_e)

            replacements.append((except_line, handler_end - 1, new_lines))
            changes.append(f"  Replaced except handler at line {handler.lineno} with BlockDependencyError (deps: {', '.join(sorted(deps))})")

    if not replacements:
        return source, []

    # Apply replacements from bottom to top to preserve line numbers
    replacements.sort(key=lambda r: r[0], reverse=True)

    for start, end, new_lines in replacements:
        source_lines[start:end + 1] = new_lines

    return "\n".join(source_lines) + "\n", changes


def find_unguarded_heavy_imports(filepath):
    """Find heavy imports inside functions that are NOT in try/except blocks."""
    with open(filepath) as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    unguarded = []

    for func_node in ast.walk(tree):
        if not isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Find all try nodes in this function
        try_nodes = set()
        for node in ast.walk(func_node):
            if isinstance(node, ast.Try):
                for child in ast.walk(node):
                    try_nodes.add(id(child))

        # Find imports not in try blocks
        for node in ast.walk(func_node):
            if id(node) in try_nodes:
                continue

            if isinstance(node, ast.Import):
                for alias in node.names:
                    if is_heavy(alias.name):
                        unguarded.append((node.lineno, f"import {alias.name}", func_node.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module and is_heavy(node.module):
                    names = ", ".join(a.name for a in node.names)
                    unguarded.append((node.lineno, f"from {node.module} import {names}", func_node.name))

    return unguarded


def main():
    blocks_dir = "blocks"
    if not os.path.isdir(blocks_dir):
        print("Error: blocks/ directory not found. Run from project root.")
        sys.exit(1)

    fixed_files = []
    skipped_files = []
    unguarded_report = []

    for root, dirs, files in sorted(os.walk(blocks_dir)):
        for f in sorted(files):
            if f != "run.py":
                continue

            filepath = os.path.join(root, f)

            # Process try/except handlers
            new_source, changes = process_file(filepath)

            if changes:
                with open(filepath, "w") as fh:
                    fh.write(new_source)
                fixed_files.append((filepath, changes))

            # Check for remaining unguarded imports
            unguarded = find_unguarded_heavy_imports(filepath)
            if unguarded:
                unguarded_report.append((filepath, unguarded))

    # Report
    print("=" * 80)
    print("FIXED FILES (try/except handler → BlockDependencyError):")
    print("=" * 80)
    for filepath, changes in fixed_files:
        print(f"\n  {filepath}:")
        for change in changes:
            print(f"    {change}")
    print(f"\n  Total files fixed: {len(fixed_files)}")

    if unguarded_report:
        print()
        print("=" * 80)
        print("REMAINING UNGUARDED IMPORTS (need manual wrapping):")
        print("=" * 80)
        for filepath, imports in unguarded_report:
            print(f"\n  {filepath}:")
            for lineno, desc, func_name in imports:
                print(f"    Line {lineno} in {func_name}(): {desc}")
        print(f"\n  Total files with unguarded imports: {len(unguarded_report)}")


if __name__ == "__main__":
    main()
