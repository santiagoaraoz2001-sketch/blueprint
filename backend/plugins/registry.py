"""
Plugin Registry — discovers, loads, and manages Blueprint plugins.

Plugins are directories in ~/.specific-labs/plugins/ with a plugin.yaml manifest.

Plugin structure:
    ~/.specific-labs/plugins/my-plugin/
        plugin.yaml          # Manifest (name, version, author, type, permissions)
        __init__.py           # Python entry point
        blocks/               # Optional: additional blocks
        frontend/             # Optional: React components (built JS)
"""

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import yaml
import importlib.util
import logging

from ..config import BASE_DIR

PLUGINS_DIR = BASE_DIR / "plugins"
logger = logging.getLogger("blueprint.plugins")

# Plugin names must be safe identifiers (letters, digits, hyphens, underscores)
_SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")

# Valid plugin types
_VALID_TYPES = {"generic", "blocks", "connector", "monitor"}

# Valid permission tokens
_VALID_PERMISSIONS = {"network", "filesystem", "gpu"}


@dataclass
class PluginManifest:
    name: str
    version: str
    author: str = ""
    description: str = ""
    plugin_type: str = "generic"  # "blocks", "connector", "monitor", "generic"
    permissions: list[str] = field(default_factory=list)  # "network", "filesystem", "gpu"
    dependencies: list[str] = field(default_factory=list)  # pip package names
    entry_point: str = "__init__"  # Python module to load
    enabled: bool = True


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    path: Path
    module: Any = None
    error: Optional[str] = None

    @property
    def is_loaded(self) -> bool:
        return self.module is not None and self.error is None


def _validate_manifest(raw: dict, plugin_dir: Path) -> PluginManifest:
    """Parse and validate a raw YAML dict into a PluginManifest.

    Raises ValueError on invalid data.
    """
    name = raw.get("name", plugin_dir.name)
    if not isinstance(name, str) or not _SAFE_NAME.match(name):
        raise ValueError(
            f"Invalid plugin name {name!r}: must be 1-64 alphanumeric/hyphen/underscore "
            f"characters, starting with a letter or digit"
        )

    version = str(raw.get("version", "0.0.0"))

    plugin_type = raw.get("type", "generic")
    if plugin_type not in _VALID_TYPES:
        raise ValueError(
            f"Invalid plugin type {plugin_type!r}: must be one of {sorted(_VALID_TYPES)}"
        )

    permissions = raw.get("permissions", [])
    if not isinstance(permissions, list):
        raise ValueError("'permissions' must be a list")
    unknown = set(permissions) - _VALID_PERMISSIONS
    if unknown:
        raise ValueError(
            f"Unknown permissions {unknown}: valid values are {sorted(_VALID_PERMISSIONS)}"
        )

    dependencies = raw.get("dependencies", [])
    if not isinstance(dependencies, list):
        raise ValueError("'dependencies' must be a list")

    entry_point = raw.get("entry_point", "__init__")
    if not isinstance(entry_point, str) or not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", entry_point):
        raise ValueError(
            f"Invalid entry_point {entry_point!r}: must be a valid Python identifier"
        )

    return PluginManifest(
        name=name,
        version=version,
        author=str(raw.get("author", "")),
        description=str(raw.get("description", "")),
        plugin_type=plugin_type,
        permissions=permissions,
        dependencies=dependencies,
        entry_point=entry_point,
        enabled=bool(raw.get("enabled", True)),
    )


def _resolve_module_path(plugin_path: Path, entry_point: str) -> Path:
    """Resolve the Python module path for a plugin entry point.

    Validates that the resolved path is within the plugin directory
    to prevent path traversal attacks.

    Raises FileNotFoundError if the module doesn't exist.
    Raises ValueError if the resolved path escapes the plugin directory.
    """
    # Try <entry_point>.py first, then <entry_point>/__init__.py
    module_path = plugin_path / f"{entry_point}.py"
    if not module_path.exists():
        module_path = plugin_path / entry_point / "__init__.py"

    if not module_path.exists():
        raise FileNotFoundError(
            f"Entry point module not found: tried {entry_point}.py and "
            f"{entry_point}/__init__.py in {plugin_path}"
        )

    # Resolve symlinks and ensure the module is within the plugin directory
    resolved = module_path.resolve()
    plugin_resolved = plugin_path.resolve()
    if not resolved.is_relative_to(plugin_resolved):
        raise ValueError(
            f"Entry point {entry_point} resolves outside plugin directory: {resolved}"
        )

    return module_path


class PluginRegistry:
    def __init__(self):
        self._plugins: dict[str, LoadedPlugin] = {}
        self._scanned = False
        self._lock = threading.Lock()

    def scan(self) -> list[LoadedPlugin]:
        """Discover all plugins in the plugins directory.

        On rescan, preserves loaded module state for plugins that still exist
        and calls unregister() on plugins that have been removed.
        """
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

        discovered: dict[str, LoadedPlugin] = {}

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
                    raise ValueError("plugin.yaml must be a YAML mapping")

                manifest = _validate_manifest(raw, plugin_dir)

                if manifest.name in discovered:
                    prev = discovered[manifest.name]
                    logger.warning(
                        "Duplicate plugin name %r: %s conflicts with %s (keeping first)",
                        manifest.name, plugin_dir, prev.path,
                    )
                    continue

                discovered[manifest.name] = LoadedPlugin(
                    manifest=manifest, path=plugin_dir
                )
            except Exception as e:
                logger.warning("Failed to read plugin manifest at %s: %s", manifest_path, e)

        with self._lock:
            previous = self._plugins

            # Preserve loaded module state for plugins that still exist at the same path
            for name, new_plugin in discovered.items():
                old_plugin = previous.get(name)
                if old_plugin and old_plugin.is_loaded and old_plugin.path == new_plugin.path:
                    new_plugin.module = old_plugin.module
                    new_plugin.error = old_plugin.error

            # Collect removed plugins that need cleanup
            removed = [
                (name, old_plugin) for name, old_plugin in previous.items()
                if name not in discovered and old_plugin.module is not None
            ]

            self._plugins = discovered
            self._scanned = True

        # Call unregister hooks outside the lock to avoid deadlock
        for name, old_plugin in removed:
            if hasattr(old_plugin.module, "unregister"):
                try:
                    old_plugin.module.unregister(self)
                except Exception as e:
                    logger.warning("Error in %s unregister() during rescan: %s", name, e)

        count = len(discovered)
        if count:
            logger.info("Discovered %d plugin(s)", count)
        return list(discovered.values())

    def load_plugin(self, name: str) -> LoadedPlugin:
        """Load a plugin's Python module."""
        with self._lock:
            plugin = self._plugins.get(name)
        if not plugin:
            raise ValueError(f"Plugin '{name}' not found")
        if not plugin.manifest.enabled:
            plugin.error = "Plugin is disabled"
            return plugin

        try:
            module_path = _resolve_module_path(plugin.path, plugin.manifest.entry_point)

            spec = importlib.util.spec_from_file_location(
                f"blueprint_plugin_{name}", str(module_path)
            )
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Cannot create module spec from {module_path}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Call plugin's register() if it exists
            if hasattr(module, "register"):
                module.register(self)

            # Set module and clear any previous error only after full success
            plugin.module = module
            plugin.error = None

            logger.info("Loaded plugin: %s v%s", name, plugin.manifest.version)
        except Exception as e:
            plugin.module = None
            plugin.error = str(e)
            logger.error("Failed to load plugin %s: %s", name, e)

        return plugin

    def unload_plugin(self, name: str) -> LoadedPlugin:
        """Unload a plugin's module and call its cleanup hook if present."""
        with self._lock:
            plugin = self._plugins.get(name)
        if not plugin:
            raise ValueError(f"Plugin '{name}' not found")

        if plugin.module is not None:
            # Call plugin's unregister/cleanup hook if it exists
            if hasattr(plugin.module, "unregister"):
                try:
                    plugin.module.unregister(self)
                except Exception as e:
                    logger.warning("Error in %s unregister(): %s", name, e)
            plugin.module = None

        return plugin

    def load_all(self):
        """Scan and load all enabled plugins."""
        if not self._scanned:
            self.scan()

        with self._lock:
            to_load = [
                name for name, plugin in self._plugins.items()
                if plugin.manifest.enabled and not plugin.is_loaded
            ]

        loaded, failed = 0, 0
        for name in to_load:
            result = self.load_plugin(name)
            if result.is_loaded:
                loaded += 1
            else:
                failed += 1

        if loaded or failed:
            logger.info("Plugin loading complete: %d loaded, %d failed", loaded, failed)

    def get_plugin(self, name: str) -> Optional[LoadedPlugin]:
        with self._lock:
            return self._plugins.get(name)

    def list_plugins(self) -> list[dict]:
        if not self._scanned:
            self.scan()
        with self._lock:
            plugins = list(self._plugins.values())
        return [
            {
                "name": p.manifest.name,
                "version": p.manifest.version,
                "author": p.manifest.author,
                "description": p.manifest.description,
                "type": p.manifest.plugin_type,
                "enabled": p.manifest.enabled,
                "loaded": p.is_loaded,
                "error": p.error,
            }
            for p in plugins
        ]

    def find_block(self, block_type: str) -> Optional[Path]:
        """Find a specific block type across all loaded plugins.

        Uses direct path lookups (category/block_type/run.py) matching the
        same structure as built-in blocks, avoiding a full directory scan.
        """
        with self._lock:
            plugins = [p for p in self._plugins.values() if p.is_loaded]

        for plugin in plugins:
            blocks_dir = plugin.path / "blocks"
            if not blocks_dir.exists():
                continue
            try:
                for cat_dir in blocks_dir.iterdir():
                    if not cat_dir.is_dir() or cat_dir.name.startswith((".", "_")):
                        continue
                    block_dir = cat_dir / block_type
                    if block_dir.is_dir() and (block_dir / "run.py").exists():
                        return block_dir
            except OSError as e:
                logger.warning(
                    "Error searching plugin blocks in %s: %s", plugin.manifest.name, e
                )
        return None

    def get_plugin_blocks(self) -> list[Path]:
        """Get all block directories provided by loaded plugins."""
        with self._lock:
            plugins = [p for p in self._plugins.values() if p.is_loaded]

        blocks = []
        for plugin in plugins:
            blocks_dir = plugin.path / "blocks"
            if not blocks_dir.exists():
                continue
            try:
                for cat_dir in blocks_dir.iterdir():
                    if not cat_dir.is_dir() or cat_dir.name.startswith((".", "_")):
                        continue
                    for block_dir in cat_dir.iterdir():
                        if not block_dir.is_dir() or block_dir.name.startswith((".", "_")):
                            continue
                        if (block_dir / "run.py").exists():
                            blocks.append(block_dir)
            except OSError as e:
                logger.warning(
                    "Error scanning plugin blocks in %s: %s", plugin.manifest.name, e
                )
        return blocks

    def plugin_info(self, name: str) -> Optional[dict]:
        """Return full info dict for a single plugin, or None if not found."""
        with self._lock:
            plugin = self._plugins.get(name)
        if not plugin:
            return None
        return {
            "name": plugin.manifest.name,
            "version": plugin.manifest.version,
            "author": plugin.manifest.author,
            "description": plugin.manifest.description,
            "type": plugin.manifest.plugin_type,
            "permissions": plugin.manifest.permissions,
            "dependencies": plugin.manifest.dependencies,
            "enabled": plugin.manifest.enabled,
            "loaded": plugin.is_loaded,
            "error": plugin.error,
            "path": str(plugin.path),
        }


# Singleton
plugin_registry = PluginRegistry()
