"""
Plugin Sandbox — lightweight permission enforcement for Blueprint plugins.

Not full process isolation, but an audit layer that:
  - Intercepts open() calls and checks filesystem permissions
  - Intercepts imports and checks network/gpu/secrets permissions
  - Blocks dangerous modules (subprocess, ctypes, etc.) unconditionally
  - Logs all permission-checked actions
  - Raises PermissionError with clear messages

Applied per-module at load time via apply_sandbox() / remove_sandbox().

Limitations (by design — this is an audit layer, not a VM):
  - A determined attacker with filesystem:read could read source and find workarounds
  - Modules already imported before sandbox is applied are not re-patched
  - Low-level C extensions can bypass Python-level hooks
  These trade-offs are acceptable for the trust model: plugins come from
  known sources and permissions serve as a declaration + enforcement layer,
  not a hard security boundary against adversarial code.
"""

import logging
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

import builtins as _builtins_module

from ..config import BASE_DIR

logger = logging.getLogger("blueprint.plugins.sandbox")

# ── Thread-safe state ──────────────────────────────────────────────────

_lock = threading.Lock()
_sandboxed_modules: dict[str, dict[str, Any]] = {}

# ── Capture real builtins once at import time ──────────────────────────

_real_open = _builtins_module.open
_real_import = _builtins_module.__import__

# ── Module classification ─────────────────────────────────────────────

# Always blocked — these provide escape hatches that bypass any audit layer.
_BLOCKED_MODULES = frozenset({
    "subprocess",   # Arbitrary command execution
    "ctypes",       # C function calls, memory access
    "pty",          # Pseudo-terminals
    "importlib",    # Can bypass import hooks
    "code",         # Interactive interpreter
    "codeop",       # Compile code interactively
})

# Require 'network' permission
_NETWORK_MODULES = frozenset({
    "requests", "urllib", "urllib3", "httpx", "aiohttp",
    "http", "socket", "socketserver",
    "xmlrpc", "ftplib", "smtplib", "poplib", "imaplib",
})

# Require 'gpu' permission
_GPU_MODULES = frozenset({
    "torch", "tensorflow", "jax", "cupy", "pycuda", "mlx",
})

# Require 'secrets' permission
_SECRETS_MODULES = frozenset({
    "keyring", "dotenv",
})

# Require 'filesystem:read' or 'filesystem:write' — these provide raw
# file-system access that bypasses our patched open().
_FILESYSTEM_MODULES = frozenset({
    "shutil", "tempfile", "glob", "fnmatch",
})


class PluginPermissionError(PermissionError):
    """Raised when a plugin attempts an action it lacks permission for."""

    def __init__(self, plugin_name: str, action: str, permission: str):
        self.plugin_name = plugin_name
        self.action = action
        self.permission = permission
        super().__init__(
            f"Plugin '{plugin_name}' tried to {action} but doesn't have "
            f"'{permission}' permission. Add '{permission}' to the plugin's "
            f"plugin.yaml permissions list."
        )


# ── Write-mode detection ──────────────────────────────────────────────

# Characters in a mode string that indicate write intent.
# Note: 'b' (binary) and 't' (text) are encoding flags, NOT access modes.
_WRITE_MODE_CHARS = frozenset("wxa+")


def _mode_is_write(mode: str) -> bool:
    """Return True if the open() mode implies write access."""
    return bool(_WRITE_MODE_CHARS & set(mode))


# ── Sandboxed open() ─────────────────────────────────────────────────

def _make_sandboxed_open(plugin_name: str, permissions: frozenset[str]):
    """Create a sandboxed open() that enforces filesystem permissions."""

    has_read = "filesystem:read" in permissions
    has_write = "filesystem:write" in permissions
    data_dir = BASE_DIR.resolve()

    def _sandboxed_open(file, mode="r", *args, **kwargs):
        # Reject file-descriptor integers — they bypass path-based checks.
        if isinstance(file, int):
            if not (has_read and has_write):
                logger.warning(
                    "Plugin '%s' denied open() on file descriptor %d",
                    plugin_name, file,
                )
                raise PluginPermissionError(
                    plugin_name,
                    f"open file descriptor {file} (fd-based access requires "
                    f"both filesystem:read and filesystem:write)",
                    "filesystem:read, filesystem:write",
                )
            return _real_open(file, mode, *args, **kwargs)

        # Resolve the path for permission checks
        try:
            path = Path(file).resolve()
        except (TypeError, ValueError):
            # If we can't resolve, let real open() produce the error
            return _real_open(file, mode, *args, **kwargs)

        is_write = _mode_is_write(mode)

        if is_write:
            if not has_write:
                logger.warning(
                    "Plugin '%s' denied write access to %s (mode=%s)",
                    plugin_name, path, mode,
                )
                raise PluginPermissionError(
                    plugin_name,
                    f"write to file '{path}'",
                    "filesystem:write",
                )
            # Even with write permission, restrict writes to the data directory
            if not path.is_relative_to(data_dir):
                logger.warning(
                    "Plugin '%s' denied write outside data dir: %s",
                    plugin_name, path,
                )
                raise PluginPermissionError(
                    plugin_name,
                    f"write to '{path}' (outside data directory {data_dir})",
                    "filesystem:write",
                )
        else:
            if not has_read:
                logger.warning(
                    "Plugin '%s' denied read access to %s", plugin_name, path,
                )
                raise PluginPermissionError(
                    plugin_name,
                    f"read file '{path}'",
                    "filesystem:read",
                )

        logger.debug(
            "Plugin '%s' opening %s (mode=%s)", plugin_name, path, mode,
        )
        return _real_open(file, mode, *args, **kwargs)

    return _sandboxed_open


# ── Sandboxed __import__() ───────────────────────────────────────────

def _make_sandboxed_import(plugin_name: str, permissions: frozenset[str]):
    """Create a sandboxed __import__ that gates restricted module access."""

    has_network = "network" in permissions
    has_gpu = "gpu" in permissions
    has_secrets = "secrets" in permissions
    has_any_fs = "filesystem:read" in permissions or "filesystem:write" in permissions

    def _sandboxed_import(name, *args, **kwargs):
        top_level = name.split(".")[0]

        # Always-blocked modules (no permission can override)
        if top_level in _BLOCKED_MODULES:
            logger.warning(
                "Plugin '%s' denied import of blocked module '%s'",
                plugin_name, name,
            )
            raise PluginPermissionError(
                plugin_name,
                f"import blocked module '{name}' (this module is never "
                f"allowed in plugins for security reasons)",
                "(blocked)",
            )

        # Network modules
        if top_level in _NETWORK_MODULES:
            if not has_network:
                logger.warning(
                    "Plugin '%s' denied import of network module '%s'",
                    plugin_name, name,
                )
                raise PluginPermissionError(
                    plugin_name,
                    f"import network module '{name}'",
                    "network",
                )
            logger.debug(
                "Plugin '%s' importing network module: %s", plugin_name, name,
            )

        # GPU modules
        if top_level in _GPU_MODULES:
            if not has_gpu:
                logger.warning(
                    "Plugin '%s' denied import of GPU module '%s'",
                    plugin_name, name,
                )
                raise PluginPermissionError(
                    plugin_name,
                    f"import GPU module '{name}'",
                    "gpu",
                )
            logger.debug(
                "Plugin '%s' importing GPU module: %s", plugin_name, name,
            )

        # Secrets modules
        if top_level in _SECRETS_MODULES:
            if not has_secrets:
                logger.warning(
                    "Plugin '%s' denied import of secrets module '%s'",
                    plugin_name, name,
                )
                raise PluginPermissionError(
                    plugin_name,
                    f"import secrets module '{name}'",
                    "secrets",
                )
            logger.debug(
                "Plugin '%s' importing secrets module: %s", plugin_name, name,
            )

        # Filesystem helper modules — require at least one fs permission
        if top_level in _FILESYSTEM_MODULES:
            if not has_any_fs:
                logger.warning(
                    "Plugin '%s' denied import of filesystem module '%s'",
                    plugin_name, name,
                )
                raise PluginPermissionError(
                    plugin_name,
                    f"import filesystem module '{name}'",
                    "filesystem:read",
                )
            logger.debug(
                "Plugin '%s' importing filesystem module: %s",
                plugin_name, name,
            )

        return _real_import(name, *args, **kwargs)

    return _sandboxed_import


# ── Public API ────────────────────────────────────────────────────────

def apply_sandbox(module: ModuleType, manifest) -> None:
    """Apply sandbox restrictions to a plugin module before it executes.

    Patches the module's ``__builtins__`` dict to intercept ``open()`` and
    ``__import__`` based on the plugin's declared permissions.

    Must be called **before** ``exec_module()`` so that module-level code
    runs under the sandbox.

    Args:
        module: The plugin module object (pre-execution).
        manifest: PluginManifest with ``name`` and ``permissions`` fields.
    """
    plugin_name = manifest.name
    permissions = frozenset(manifest.permissions)

    logger.info(
        "Applying sandbox to plugin '%s' (permissions: %s)",
        plugin_name, sorted(permissions),
    )

    # Build a copy of the real builtins with our patched versions
    patched_builtins = dict(vars(_builtins_module))
    patched_builtins["open"] = _make_sandboxed_open(plugin_name, permissions)
    patched_builtins["__import__"] = _make_sandboxed_import(
        plugin_name, permissions,
    )

    # Setting __builtins__ on the module makes Python use this dict
    # for all builtin lookups within that module's code.
    module.__builtins__ = patched_builtins

    with _lock:
        _sandboxed_modules[plugin_name] = {
            "permissions": permissions,
        }

    logger.debug("Sandbox applied to plugin '%s'", plugin_name)


def remove_sandbox(module: ModuleType, manifest) -> None:
    """Remove sandbox tracking for a plugin module.

    The module object itself is being discarded by the caller, so we only
    need to clean up our tracking dict.

    Args:
        module: The plugin module.
        manifest: PluginManifest with ``name``.
    """
    plugin_name = manifest.name

    with _lock:
        removed = _sandboxed_modules.pop(plugin_name, None)

    if removed:
        logger.debug("Sandbox removed from plugin '%s'", plugin_name)


def get_sandbox_log(plugin_name: str) -> dict:
    """Get sandbox status info for a plugin.

    Returns:
        Dict with ``sandboxed`` bool and ``permissions`` list.
    """
    with _lock:
        info = _sandboxed_modules.get(plugin_name)

    if not info:
        return {"sandboxed": False, "permissions": []}
    return {
        "sandboxed": True,
        "permissions": sorted(info["permissions"]),
    }
