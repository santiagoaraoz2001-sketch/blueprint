"""W&B Monitor Plugin — streams metrics to W&B during training.

This is the entry-point module loaded by the plugin registry.  It exposes two
lifecycle hooks:

* ``register(registry)``   — called when the plugin is loaded / enabled.
* ``unregister(registry)`` — called when the plugin is unloaded / disabled.
"""

import logging

_logger = logging.getLogger("blueprint.plugins.wandb")


def register(registry):
    """Called by the plugin registry when the plugin is loaded.

    Plugin blocks are auto-discovered from the ``blocks/`` directory, so
    registration here is limited to logging.
    """
    _logger.info("W&B Monitor plugin loaded")


def unregister(registry):
    """Called by the plugin registry when the plugin is unloaded or disabled.

    Finishes any active W&B run so it does not leak as an orphaned
    "running" entry on the W&B dashboard.
    """
    try:
        import wandb

        if wandb.run is not None:
            _logger.info("Finishing active W&B run on plugin unload")
            wandb.finish()
    except Exception:
        # Best-effort cleanup — swallow errors during shutdown.
        pass
