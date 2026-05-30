"""
Live STT Service

Streams 1–2 second WAV chunks to the Azure gpt-4o-transcribe-diarize endpoint
and returns (text, speaker_label, duration_ms) per chunk.

Uses the AZURE_STT_LABEL_* credentials (separate from the existing
azure_stt_* batch credentials) as specified in the design doc.

The public entry point is:
    transcribe_chunk(audio_bytes, filename) -> list[DiarizedSegment]
"""

from __future__ import annotations

import os
import json
import logging
import time
from typing import Optional

import httpx

from config import get_settings

logger = logging.getLogger(__name__)


class DiarizedSegment:
    """A single speaker-labelled transcription segment."""

    __slots__ = ("text", "speaker_label", "timestamp", "duration_ms")

    def __init__(
        self,
        text: str,
        speaker_label: str,
        timestamp: float,
        duration_ms: int = 0,
    ) -> None:
        self.text         = text
        self.speaker_label = speaker_label
        self.timestamp    = timestamp
        self.duration_ms  = duration_ms

    def __repr__(self) -> str:
        return (
            f"DiarizedSegment(speaker={self.speaker_label!r}, "
            f"text={self.text[:40]!r})"
        )


async def transcribe_chunk(
    audio_bytes: bytes,
    filename: str = "chunk.wav",
) -> list[DiarizedSegment]:
    """
    Send a short audio chunk to Azure STT with diarization enabled.

    Returns a list of DiarizedSegment objects (one per speaker turn
    detected within the chunk). In most 1-2s chunks this will be a
    single segment.

    Falls back to the existing azure_stt endpoint if the
    azure_stt_label endpoint is not configured.
    """
    settings = get_settings()

    # Prefer the new label endpoint; fall back to the existing one
    endpoint   = settings.azure_stt_label_endpoint or settings.azure_stt_endpoint
    api_key    = settings.azure_stt_label_api_key  or settings.azure_stt_api_key
    deployment = settings.azure_stt_label_deployment or settings.azure_stt_deployment

    if not endpoint:
        logger.error("No Azure STT endpoint configured.")
        return []

    headers = {"api-key": api_key}
    files   = {"file": (filename, audio_bytes, "application/octet-stream")}
    data    = {
        "model": deployment,
        # Request verbose JSON so we get per-segment speaker labels
        "response_format": "verbose_json",
        "timestamp_granularities[]": "segment",
    }

    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")

    now = time.time()

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            proxy=proxy_url,
            verify=False,
        ) as client:
            resp = await client.post(endpoint, headers=headers, files=files, data=data)
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("Azure STT HTTP error %s: %s", exc.response.status_code, exc.response.text[:200])
        return []
    except Exception as exc:
        logger.error("Azure STT request failed: %s", exc)
        return []

    # ── Parse diarized response ───────────────────────────────────────────────
    segments: list[DiarizedSegment] = []

    # verbose_json response shape:
    # {
    #   "text": "...",
    #   "segments": [
    #     {
    #       "text": "...",
    #       "start": 0.0,
    #       "end": 1.2,
    #       "speaker": "SPEAKER_00" | "speaker_0" | ...
    #     }, ...
    #   ]
    # }

    raw_segments = result.get("segments") or []

    if raw_segments:
        for seg in raw_segments:
            text = (seg.get("text") or "").strip()
            if not text:
                continue

            # Azure uses different key names depending on model/version
            speaker = (
                seg.get("speaker")
                or seg.get("speaker_label")
                or seg.get("diarization", {}).get("speaker", "speaker_0")
            )
            # Normalise to lowercase underscore format: "speaker_0"
            speaker = speaker.lower().replace("speaker_", "speaker_").replace(" ", "_")
            if not speaker.startswith("speaker_"):
                speaker = f"speaker_{speaker}"

            start_s = seg.get("start", 0.0)
            end_s   = seg.get("end", start_s)
            duration = int((end_s - start_s) * 1000)

            segments.append(DiarizedSegment(
                text=text,
                speaker_label=speaker,
                timestamp=now + start_s,
                duration_ms=duration,
            ))
    else:
        # Fallback: no segment info — treat entire chunk as a single unknown speaker
        full_text = (result.get("text") or "").strip()
        if full_text:
            segments.append(DiarizedSegment(
                text=full_text,
                speaker_label="speaker_0",
                timestamp=now,
                duration_ms=0,
            ))

    return segments
