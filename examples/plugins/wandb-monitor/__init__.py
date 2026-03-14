"""W&B Monitor Plugin — streams metrics to W&B during training."""


def register(registry):
    """Called by plugin registry on load."""
    # Plugin blocks are auto-discovered from blocks/ directory
    # Just log that we're loaded
    import logging
    logging.getLogger("blueprint.plugins.wandb").info("W&B Monitor plugin loaded")
