"""Application configuration, loaded from environment or a local .env file."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Criminal Law Q&A Assistant"
    environment: Literal["development", "production"] = "development"

    # Which provider serves requests. See docs/adr/0003-llm-provider-strategy.md
    llm_provider: Literal["groq", "ollama"] = "groq"

    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_chat_model: str = "llama-3.3-70b-versatile"
    groq_vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    groq_transcription_model: str = "whisper-large-v3"

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_chat_model: str = "qwen2.5:3b-instruct"

    # Generation defaults. Temperature is zero because answers must be reproducible
    # across evaluation runs; a varying answer cannot be regression-tested.
    temperature: float = 0.0
    max_tokens: int = 1024

    request_timeout_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
