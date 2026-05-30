"""
Azure STT integration — sends audio to gpt-4o-transcribe and returns text.
"""

import os
import httpx
from config import get_settings


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """
    Send an audio file to Azure gpt-4o-transcribe for transcription.

    Parameters
    ----------
    audio_bytes : bytes
        Raw audio file content (webm, wav, mp3, etc.)
    filename : str
        Original filename — the extension helps Azure pick the right codec.

    Returns
    -------
    str
        Transcribed text.
    """
    settings = get_settings()

    headers = {
        "api-key": settings.azure_stt_api_key,
    }

    # The endpoint already contains deployment + api-version in the URL
    url = settings.azure_stt_endpoint

    files = {
        "file": (filename, audio_bytes, "application/octet-stream"),
    }

    data = {
        "model": settings.azure_stt_deployment,
    }

    proxy_url = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    async with httpx.AsyncClient(
        timeout=60.0,
        proxy=proxy_url,
        verify=False,  # corporate proxy may intercept TLS
    ) as client:
        response = await client.post(
            url,
            headers=headers,
            files=files,
            data=data,
        )
        response.raise_for_status()

    result = response.json()
    return result.get("text", "").strip()
