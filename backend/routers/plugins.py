import logging
import os
import tempfile

import yaml
from fastapi import APIRouter, HTTPException

from ..plugins.registry import plugin_registry

router = APIRouter(prefix="/api/plugins", tags=["plugins"])
logger = logging.getLogger("blueprint.plugins")


def _persist_enabled_flag(plugin, enabled: bool):
    """Atomically update the 'enabled' flag in a plugin's plugin.yaml."""
    manifest_path = plugin.path / "plugin.yaml"
    try:
        with open(manifest_path) as f:
            raw = yaml.safe_load(f) or {}
        raw["enabled"] = enabled
        # Atomic write: write to temp file in the same directory, then rename.
        # os.rename is atomic on POSIX when src and dst are on the same filesystem.
        fd, tmp_path = tempfile.mkstemp(
            dir=str(plugin.path), suffix=".yaml.tmp", prefix=".plugin_"
        )
        try:
            with os.fdopen(fd, "w") as f:
                yaml.safe_dump(raw, f, default_flow_style=False)
            os.rename(tmp_path, str(manifest_path))
        except BaseException:
            # Clean up temp file on any failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        logger.warning("Failed to persist enabled=%s for plugin %s: %s",
                        enabled, plugin.manifest.name, e)


@router.get("/")
def list_plugins():
    return {"plugins": plugin_registry.list_plugins()}


@router.get("/{name}")
def get_plugin(name: str):
    info = plugin_registry.plugin_info(name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    return info


@router.post("/rescan")
def rescan_plugins():
    """Re-scan the plugins directory for new or removed plugins."""
    plugins = plugin_registry.scan()
    return {
        "status": "scanned",
        "count": len(plugins),
        "plugins": plugin_registry.list_plugins(),
    }


@router.post("/{name}/enable")
def enable_plugin(name: str):
    plugin = plugin_registry.get_plugin(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    plugin.manifest.enabled = True
    _persist_enabled_flag(plugin, True)

    # Clear previous error and attempt to load
    plugin.error = None
    plugin_registry.load_plugin(name)

    info = plugin_registry.plugin_info(name)
    return {"status": "enabled", "plugin": info}


@router.post("/{name}/disable")
def disable_plugin(name: str):
    plugin = plugin_registry.get_plugin(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    plugin.manifest.enabled = False
    plugin_registry.unload_plugin(name)
    _persist_enabled_flag(plugin, False)

    info = plugin_registry.plugin_info(name)
    return {"status": "disabled", "plugin": info}
