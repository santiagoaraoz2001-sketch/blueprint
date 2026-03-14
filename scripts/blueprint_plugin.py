#!/usr/bin/env python3
"""
Blueprint Plugin CLI — install, remove, list, create, and inspect plugins.

Usage:
    python -m scripts.blueprint_plugin list
    python -m scripts.blueprint_plugin install <source> [--yes]
    python -m scripts.blueprint_plugin remove <name> [--yes]
    python -m scripts.blueprint_plugin create <name> [--type TYPE]
    python -m scripts.blueprint_plugin info <name>
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

# Resolve data directory (same logic as backend/config.py)
BASE_DIR = Path(os.environ.get("BLUEPRINT_DATA_DIR", Path.home() / ".specific-labs"))
PLUGINS_DIR = BASE_DIR / "plugins"

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
_VALID_TYPES = {"generic", "blocks", "connector", "monitor"}
_VALID_PERMISSIONS = {
    "network", "filesystem", "filesystem:read", "filesystem:write",
    "gpu", "secrets",
}


# ── Helpers ───────────────────────────────────────────────────────────

def _error(msg: str):
    """Print an error message and exit with status 1."""
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def _info(msg: str):
    """Print an informational line."""
    print(f"  {msg}")


def _validate_plugin_name(name: str) -> None:
    """Validate a plugin name or exit with an error.

    Prevents path traversal (e.g. ``../../foo``) and enforces the naming
    convention used by the registry.
    """
    if not _SAFE_NAME.match(name):
        _error(
            f"Invalid plugin name '{name}': must be 1-64 alphanumeric, "
            f"hyphen, or underscore characters, starting with a letter or digit."
        )


def _resolve_plugin_dir(name: str) -> Path:
    """Return the plugin directory for *name*, validating it is inside PLUGINS_DIR."""
    _validate_plugin_name(name)
    dest = (PLUGINS_DIR / name).resolve()
    # Defence-in-depth: even after regex validation, confirm we stay inside PLUGINS_DIR
    plugins_resolved = PLUGINS_DIR.resolve()
    if not dest.is_relative_to(plugins_resolved):
        _error(f"Plugin path escapes plugins directory: {dest}")
    return dest


def _load_manifest(plugin_dir: Path) -> dict:
    """Load and return the raw manifest dict from a plugin directory."""
    manifest_path = plugin_dir / "plugin.yaml"
    if not manifest_path.exists():
        _error(f"No plugin.yaml found in {plugin_dir}")
    try:
        with open(manifest_path) as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        _error(f"Invalid YAML in {manifest_path}: {e}")
    if not isinstance(raw, dict):
        _error(f"plugin.yaml in {plugin_dir} is not a valid YAML mapping")
    return raw


def _validate_manifest(raw: dict, plugin_dir: Path) -> None:
    """Validate manifest fields or exit with an error."""
    name = raw.get("name", plugin_dir.name)
    _validate_plugin_name(str(name))

    plugin_type = raw.get("type", "generic")
    if plugin_type not in _VALID_TYPES:
        _error(f"Invalid plugin type '{plugin_type}': must be one of {sorted(_VALID_TYPES)}")

    permissions = raw.get("permissions", [])
    if not isinstance(permissions, list):
        _error("'permissions' must be a list")
    for i, perm in enumerate(permissions):
        if not isinstance(perm, str):
            _error(f"permissions[{i}] must be a string, got {type(perm).__name__}")
    unknown = set(permissions) - _VALID_PERMISSIONS
    if unknown:
        _error(f"Unknown permissions {unknown}: valid values are {sorted(_VALID_PERMISSIONS)}")

    dependencies = raw.get("dependencies", [])
    if not isinstance(dependencies, list):
        _error("'dependencies' must be a list")
    for i, dep in enumerate(dependencies):
        if not isinstance(dep, str) or not dep.strip():
            _error(f"dependencies[{i}] must be a non-empty string")

    entry_point = raw.get("entry_point", "__init__")
    if not isinstance(entry_point, str) or not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", entry_point):
        _error(f"Invalid entry_point '{entry_point}': must be a valid Python identifier")


def _confirm(prompt: str, default_yes: bool = False) -> bool:
    """Prompt for yes/no confirmation. Returns True on yes."""
    suffix = "[Y/n]" if default_yes else "[y/N]"
    try:
        response = input(f"  {prompt} {suffix} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if default_yes:
        return response not in ("n", "no")
    return response in ("y", "yes")


# ── Commands ─────────────────────────────────────────────────────────

def cmd_list(args):
    """List installed plugins."""
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

    plugins = []
    for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name.startswith((".", "_")):
            continue
        manifest_path = plugin_dir / "plugin.yaml"
        if not manifest_path.exists():
            continue
        try:
            with open(manifest_path) as f:
                raw = yaml.safe_load(f) or {}
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name", plugin_dir.name))
            version = str(raw.get("version", "0.0.0"))
            ptype = str(raw.get("type", "generic"))
            enabled = bool(raw.get("enabled", True))
            desc = str(raw.get("description", ""))
            plugins.append((name, version, ptype, enabled, desc))
        except Exception as e:
            print(f"  Warning: failed to read {manifest_path}: {e}", file=sys.stderr)

    if not plugins:
        print("No plugins installed.")
        print(f"  Plugin directory: {PLUGINS_DIR}")
        return

    print(f"Installed plugins ({len(plugins)}):\n")
    name_w = max(len(p[0]) for p in plugins)
    ver_w = max(len(str(p[1])) for p in plugins)
    for name, version, ptype, enabled, desc in plugins:
        status = "enabled" if enabled else "disabled"
        line = f"  {name:<{name_w}}  v{version:<{ver_w}}  [{ptype}]  ({status})"
        if desc:
            line += f"  - {desc}"
        print(line)


def cmd_install(args):
    """Install a plugin from a git repo or local directory."""
    source = args.source
    non_interactive = args.yes

    # Determine if source is a git URL or local path
    is_git = source.startswith(("http://", "https://", "git@", "git://"))
    source_path = None
    tmp_dir = None

    try:
        if is_git:
            import tempfile
            tmp_dir = Path(tempfile.mkdtemp(prefix="blueprint_plugin_"))
            print(f"Cloning {source}...")
            try:
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", source, str(tmp_dir / "repo")],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    _error(f"git clone failed:\n{result.stderr.strip()}")
                source_path = tmp_dir / "repo"
            except FileNotFoundError:
                _error("git is not installed or not in PATH")
            except subprocess.TimeoutExpired:
                _error("git clone timed out after 120 seconds")
        else:
            source_path = Path(source).resolve()
            if not source_path.is_dir():
                _error(f"Source directory does not exist: {source_path}")

        # Validate plugin.yaml exists and is well-formed
        raw = _load_manifest(source_path)
        _validate_manifest(raw, source_path)

        name = str(raw.get("name", source_path.name))
        version = str(raw.get("version", "0.0.0"))
        permissions = raw.get("permissions", [])
        dependencies = raw.get("dependencies", [])

        # Resolve destination with path traversal protection
        dest = _resolve_plugin_dir(name)

        if dest.exists():
            _error(
                f"Plugin '{name}' is already installed at {dest}. "
                f"Remove it first with: python -m scripts.blueprint_plugin remove {name}"
            )

        # Show permission summary and confirm before installing
        if permissions:
            print(f"\n  Plugin '{name}' requests the following permissions:")
            for p in permissions:
                print(f"    - {p}")

        if not non_interactive:
            if not _confirm(f"Install plugin '{name}' v{version}?", default_yes=True):
                print("  Cancelled.")
                return

        # Copy to plugins directory
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        print(f"  Installing plugin '{name}' v{version}...")
        shutil.copytree(str(source_path), str(dest))

        # Remove .git directory if cloned from git
        git_dir = dest / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir)

        _info(f"Copied to {dest}")

        # Check dependencies
        if dependencies:
            print(f"\n  Dependencies: {', '.join(dependencies)}")
            if non_interactive or _confirm("Install dependencies with pip?", default_yes=True):
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install"] + dependencies,
                    capture_output=True, text=True, timeout=300,
                )
                if result.returncode == 0:
                    _info("Dependencies installed successfully")
                else:
                    print(
                        f"  Warning: pip install failed:\n{result.stderr.strip()}",
                        file=sys.stderr,
                    )
                    print(f"  Install manually: pip install {' '.join(dependencies)}")

        # Run plugin's validate() — in a subprocess for isolation
        entry_point = raw.get("entry_point", "__init__")
        module_path = dest / f"{entry_point}.py"
        if not module_path.exists():
            module_path = dest / entry_point / "__init__.py"

        if module_path.exists():
            validate_script = (
                f"import importlib.util, sys\n"
                f"spec = importlib.util.spec_from_file_location('_v', {str(module_path)!r})\n"
                f"if spec and spec.loader:\n"
                f"    mod = importlib.util.module_from_spec(spec)\n"
                f"    spec.loader.exec_module(mod)\n"
                f"    if hasattr(mod, 'validate'):\n"
                f"        mod.validate()\n"
                f"        print('OK')\n"
            )
            try:
                result = subprocess.run(
                    [sys.executable, "-c", validate_script],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0 and "OK" in result.stdout:
                    _info("Plugin validation passed")
                elif result.returncode != 0:
                    print(
                        f"  Warning: plugin validation failed: {result.stderr.strip()}",
                        file=sys.stderr,
                    )
            except subprocess.TimeoutExpired:
                print("  Warning: plugin validation timed out", file=sys.stderr)

        print(f"\n  Plugin '{name}' installed successfully.")
        print(f"  Enable it via the UI or API: POST /api/plugins/{name}/enable")

    finally:
        # Always clean up temp directory
        if tmp_dir is not None and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


def cmd_remove(args):
    """Remove an installed plugin."""
    name = args.name
    dest = _resolve_plugin_dir(name)

    if not dest.exists():
        _error(f"Plugin '{name}' is not installed (not found at {dest})")

    if not args.yes:
        if not _confirm(f"Remove plugin '{name}' from {dest}?"):
            print("  Cancelled.")
            return

    shutil.rmtree(dest)
    print(f"  Plugin '{name}' removed.")


def cmd_create(args):
    """Create a new plugin scaffold."""
    name = args.name
    plugin_type = args.type

    _validate_plugin_name(name)
    if plugin_type not in _VALID_TYPES:
        _error(f"Invalid plugin type '{plugin_type}': must be one of {sorted(_VALID_TYPES)}")

    dest = _resolve_plugin_dir(name)
    if dest.exists():
        _error(f"Plugin directory already exists: {dest}")

    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    dest.mkdir()

    # Generate plugin.yaml
    manifest = {
        "name": name,
        "version": "0.1.0",
        "author": "",
        "description": f"A {plugin_type} plugin for Blueprint",
        "type": plugin_type,
        "permissions": [],
        "dependencies": [],
        "entry_point": "__init__",
        "enabled": True,
    }
    with open(dest / "plugin.yaml", "w") as f:
        yaml.safe_dump(manifest, f, default_flow_style=False, sort_keys=False)

    # Generate __init__.py
    init_content = textwrap.dedent(f'''\
        """
        {name} — a Blueprint {plugin_type} plugin.
        """

        import logging

        logger = logging.getLogger("blueprint.plugins.{name}")


        def register(registry):
            """Called when the plugin is loaded.

            Args:
                registry: PluginRegistry instance.
            """
            logger.info("{name} plugin registered")


        def unregister(registry):
            """Called when the plugin is unloaded.

            Args:
                registry: PluginRegistry instance.
            """
            logger.info("{name} plugin unregistered")
    ''')
    (dest / "__init__.py").write_text(init_content)

    # Generate README.md
    readme_content = textwrap.dedent(f"""\
        # {name}

        A {plugin_type} plugin for Blueprint.

        ## Installation

        ```bash
        python -m scripts.blueprint_plugin install ./{name}
        ```

        ## Configuration

        Edit `plugin.yaml` to configure permissions, dependencies, and metadata.

        ## Development

        - `__init__.py` — Plugin entry point with `register()` and `unregister()` hooks.
        - `plugin.yaml` — Plugin manifest.
    """)
    (dest / "README.md").write_text(readme_content)

    print(f"  Plugin scaffold created at {dest}/")
    print(f"    plugin.yaml    (manifest)")
    print(f"    __init__.py    (entry point)")
    print(f"    README.md      (documentation)")


def cmd_info(args):
    """Show detailed plugin information."""
    name = args.name
    dest = _resolve_plugin_dir(name)

    if not dest.exists():
        _error(f"Plugin '{name}' is not installed (not found at {dest})")

    raw = _load_manifest(dest)

    print(f"\n  Plugin: {raw.get('name', name)}")
    print(f"  Version: {raw.get('version', '0.0.0')}")
    print(f"  Author: {raw.get('author', '(none)')}")
    print(f"  Type: {raw.get('type', 'generic')}")
    print(f"  Description: {raw.get('description', '(none)')}")
    print(f"  Enabled: {raw.get('enabled', True)}")
    print(f"  Entry point: {raw.get('entry_point', '__init__')}")
    print(f"  Path: {dest}")

    permissions = raw.get("permissions", [])
    if permissions:
        print(f"  Permissions:")
        for p in permissions:
            print(f"    - {p}")
    else:
        print(f"  Permissions: (none)")

    dependencies = raw.get("dependencies", [])
    if dependencies:
        print(f"  Dependencies:")
        for d in dependencies:
            print(f"    - {d}")
    else:
        print(f"  Dependencies: (none)")

    # List files
    files = sorted(f.relative_to(dest) for f in dest.rglob("*") if f.is_file())
    if files:
        print(f"  Files ({len(files)}):")
        for f in files[:20]:
            print(f"    {f}")
        if len(files) > 20:
            print(f"    ... and {len(files) - 20} more")
    print()


# ── Argument parsing ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="blueprint_plugin",
        description="Blueprint Plugin Manager — install, remove, list, and create plugins.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    subparsers.add_parser("list", help="List installed plugins")

    # install
    p_install = subparsers.add_parser(
        "install", help="Install a plugin from git repo or local directory",
    )
    p_install.add_argument("source", help="Git URL or local directory path")
    p_install.add_argument(
        "-y", "--yes", action="store_true",
        help="Skip confirmation prompts (for non-interactive / CI use)",
    )

    # remove
    p_remove = subparsers.add_parser("remove", help="Remove an installed plugin")
    p_remove.add_argument("name", help="Plugin name")
    p_remove.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt",
    )

    # create
    p_create = subparsers.add_parser("create", help="Create a new plugin scaffold")
    p_create.add_argument("name", help="Plugin name")
    p_create.add_argument(
        "--type", dest="type", default="generic",
        choices=sorted(_VALID_TYPES),
        help="Plugin type (default: generic)",
    )

    # info
    p_info = subparsers.add_parser("info", help="Show plugin details")
    p_info.add_argument("name", help="Plugin name")

    args = parser.parse_args()

    dispatch = {
        "list": cmd_list,
        "install": cmd_install,
        "remove": cmd_remove,
        "create": cmd_create,
        "info": cmd_info,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
