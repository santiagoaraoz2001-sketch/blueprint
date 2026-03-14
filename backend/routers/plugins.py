import logging
import os
import re
import tempfile

import yaml
from fastapi import APIRouter, HTTPException, Path as PathParam

from ..plugins.registry import plugin_registry
from ..plugins.sandbox import get_sandbox_log

router = APIRouter(prefix="/api/plugins", tags=["plugins"])
logger = logging.getLogger("blueprint.plugins")

# Matches the registry's name pattern — defence-in-depth against
# crafted path-component names.
_SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def _validated_name(name: str) -> str:
    """Validate plugin name from URL path and return it.

    Raises HTTPException 400 if the name is not a safe identifier.
    """
    if not _SAFE_NAME.match(name):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid plugin name '{name}': must be 1-64 alphanumeric, "
                f"hyphen, or underscore characters."
            ),
        )
    return name


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
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        logger.warning(
            "Failed to persist enabled=%s for plugin %s: %s",
            enabled, plugin.manifest.name, e,
        )


@router.get("/")
def list_plugins():
    return {"plugins": plugin_registry.list_plugins()}


@router.get("/{name}")
def get_plugin(name: str):
    name = _validated_name(name)
    info = plugin_registry.plugin_info(name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    info["sandbox"] = get_sandbox_log(name)
    return info


@router.get("/{name}/permissions")
def get_plugin_permissions(name: str):
    """Return permission details for the frontend confirmation dialog.

    Frontend shows this before enabling a plugin:
    "Plugin 'wandb-monitor' requests: Network access, Secret key access. Allow?"
    """
    name = _validated_name(name)
    plugin = plugin_registry.get_plugin(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    permission_labels = {
        "network": "Network access (HTTP requests)",
        "filesystem:read": "Read files in data directory",
        "filesystem:write": "Write files to data directory",
        "gpu": "GPU resource access",
        "secrets": "Access stored API keys",
    }

    return {
        "name": plugin.manifest.name,
        "version": plugin.manifest.version,
        "description": plugin.manifest.description,
        "permissions": [
            {"key": p, "label": permission_labels.get(p, p)}
            for p in plugin.manifest.permissions
        ],
        "dependencies": plugin.manifest.dependencies,
        "enabled": plugin.manifest.enabled,
    }


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
    name = _validated_name(name)
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
    name = _validated_name(name)
    plugin = plugin_registry.get_plugin(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    plugin.manifest.enabled = False
    plugin_registry.unload_plugin(name)
    _persist_enabled_flag(plugin, False)

    info = plugin_registry.plugin_info(name)
    return {"status": "disabled", "plugin": info}
