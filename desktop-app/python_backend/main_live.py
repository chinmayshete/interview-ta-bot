"""
main_live.py — Single entry point for registering the live-interview pipeline.

Usage in main.py (two lines only):
    from main_live import register_live_router
    register_live_router(app)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_live_router(app) -> None:
    """
    Patch settings, import the live router, and mount it on the app.
    Safe to call once at startup.
    """
    from config_live import patch_settings
    patch_settings()

    from routers.live_router import router
    app.include_router(router)

    logger.info("[Live] /api/live router registered.")
