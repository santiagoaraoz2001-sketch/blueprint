"""Plugin Registry — manages plugin lifecycle and panel registration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LoadedPlugin:
    """Metadata for a loaded plugin."""
    name: str
    version: str = "0.0.0"
    is_loaded: bool = False


@dataclass
class PanelDefinition:
    """A panel registered by a plugin for display in the Monitor view."""
    id: str
    name: str
    plugin: str
    component_url: str
    default_size: dict[str, int] = field(default_factory=lambda: {"width": 2, "height": 1})
    config_fields: list[dict[str, Any]] = field(default_factory=list)


class PluginRegistry:
    """Central registry for plugins and their UI panels."""

    def __init__(self) -> None:
        self._plugins: dict[str, LoadedPlugin] = {}
        self._panels: list[PanelDefinition] = []

    # ── Plugin lifecycle ──────────────────────────────────────────────

    def register_plugin(self, name: str, *, version: str = "0.0.0") -> LoadedPlugin:
        """Register a plugin and mark it as loaded."""
        plugin = LoadedPlugin(name=name, version=version, is_loaded=True)
        self._plugins[name] = plugin
        return plugin

    def unregister_plugin(self, name: str) -> None:
        """Remove a plugin and all its panels."""
        self._plugins.pop(name, None)
        self._panels = [p for p in self._panels if p.plugin != name]

    def get_plugin(self, name: str) -> LoadedPlugin | None:
        return self._plugins.get(name)

    def list_plugins(self) -> list[LoadedPlugin]:
        return list(self._plugins.values())

    # ── Panel registration ────────────────────────────────────────────

    def register_panel(self, panel: dict[str, Any]) -> None:
        """Register a UI panel from a plugin.

        Required keys: id, name, plugin, component_url
        Optional keys: default_size, config_fields

        Raises ValueError if required keys are missing.
        """
        _REQUIRED = ("id", "name", "plugin", "component_url")
        missing = [k for k in _REQUIRED if k not in panel]
        if missing:
            raise ValueError(
                f"Panel registration missing required keys: {', '.join(missing)}"
            )

        component_url = str(panel["component_url"]).strip()
        if not component_url:
            raise ValueError("Panel component_url must not be empty")

        default_size = panel.get("default_size", {"width": 2, "height": 1})
        if not isinstance(default_size, dict) or "width" not in default_size or "height" not in default_size:
            default_size = {"width": 2, "height": 1}
        # Clamp to valid grid bounds
        default_size = {
            "width": max(1, min(2, int(default_size["width"]))),
            "height": max(1, min(5, int(default_size["height"]))),
        }

        # Validate config_fields entries
        raw_fields = panel.get("config_fields", [])
        config_fields: list[dict[str, Any]] = []
        if isinstance(raw_fields, list):
            for i, entry in enumerate(raw_fields):
                if not isinstance(entry, dict):
                    raise ValueError(f"config_fields[{i}] must be a dict")
                if "name" not in entry or "type" not in entry:
                    raise ValueError(
                        f"config_fields[{i}] must have 'name' and 'type' keys"
                    )
                config_fields.append(entry)

        defn = PanelDefinition(
            id=str(panel["id"]),
            name=str(panel["name"]),
            plugin=str(panel["plugin"]),
            component_url=component_url,
            default_size=default_size,
            config_fields=config_fields,
        )
        # Replace if panel with same id exists
        self._panels = [p for p in self._panels if p.id != defn.id]
        self._panels.append(defn)

    def get_panels(self) -> list[dict[str, Any]]:
        """Return panels whose owning plugin is currently loaded."""
        result = []
        for panel in self._panels:
            plugin = self._plugins.get(panel.plugin)
            if plugin and plugin.is_loaded:
                result.append({
                    "id": panel.id,
                    "name": panel.name,
                    "plugin": panel.plugin,
                    "component_url": panel.component_url,
                    "default_size": panel.default_size,
                    "config_fields": panel.config_fields,
                })
        return result


# Module-level singleton
plugin_registry = PluginRegistry()
