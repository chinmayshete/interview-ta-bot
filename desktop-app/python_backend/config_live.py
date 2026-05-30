"""
config_live.py — Extends the existing Settings with live-interview STT credentials.

IMPORTANT: This file does NOT modify config.py.
It monkey-patches the Settings class after import so all existing code continues
to call get_settings() and receives the enriched object.

Usage in live modules:
    from config_live import patch_settings
    patch_settings()   # call once at startup (done in main_live.py)

After patching, get_settings() returns an object that also has:
    .azure_stt_label_endpoint
    .azure_stt_label_deployment
    .azure_stt_label_api_key
"""

from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)


def patch_settings() -> None:
    """
    Add live-STT fields to the cached Settings singleton.
    Safe to call multiple times (idempotent).
    """
    from config import get_settings

    settings = get_settings()

    # Only patch once
    if hasattr(settings, "_live_patched"):
        return

    # Read from environment directly (pydantic-settings won't re-read after init)
    setattr(
        settings,
        "azure_stt_label_endpoint",
        os.environ.get("AZURE_STT_LABEL_ENDPOINT", ""),
    )
    setattr(
        settings,
        "azure_stt_label_deployment",
        os.environ.get("AZURE_STT_LABEL_DEPLOYMENT", "gpt-4o-transcribe-diarize"),
    )
    setattr(
        settings,
        "azure_stt_label_api_key",
        os.environ.get("AZURE_STT_LABEL_API_KEY", ""),
    )
    setattr(settings, "_live_patched", True)

    logger.info(
        "[Live Config] STT label endpoint: %s",
        getattr(settings, "azure_stt_label_endpoint", "")[:60] or "(not set)",
    )
