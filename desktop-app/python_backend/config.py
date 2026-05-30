"""
Application configuration — loads environment variables via pydantic-settings.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Central configuration loaded from .env file."""

    # Azure OpenAI — GPT-4.1
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_gpt41_deployment: str = "gpt-4.1"

    # Azure STT — gpt-4o-transcribe
    azure_stt_endpoint: str = ""
    azure_stt_deployment: str = "gpt-4o-transcribe-diarize"
    azure_stt_api_key: str = ""

    # Azure STT Labeling (Live Interview)
    azure_stt_label_endpoint: str = ""
    azure_stt_label_deployment: str = "gpt-4o-transcribe-diarize"
    azure_stt_label_api_key: str = ""

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "allow"}


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
