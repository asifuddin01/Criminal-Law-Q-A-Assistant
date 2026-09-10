"""Construction of the configured provider.

This is the only module that knows which concrete providers exist.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.llm.base import Capability, LLMProvider
from app.llm.openai_compatible import OpenAICompatibleProvider


def _build_groq(settings: Settings) -> LLMProvider:
    if not settings.groq_api_key:
        raise RuntimeError(
            "llm_provider is 'groq' but GROQ_API_KEY is not set. "
            "Set it in backend/.env, or set LLM_PROVIDER=ollama to run locally."
        )
    return OpenAICompatibleProvider(
        name="groq",
        base_url=settings.groq_base_url,
        api_key=settings.groq_api_key,
        chat_model=settings.groq_chat_model,
        vision_model=settings.groq_vision_model,
        transcription_model=settings.groq_transcription_model,
        capabilities=frozenset(
            {Capability.TEXT, Capability.VISION, Capability.TRANSCRIPTION}
        ),
        default_temperature=settings.temperature,
        default_max_tokens=settings.max_tokens,
        timeout=settings.request_timeout_seconds,
    )


def _build_ollama(settings: Settings) -> LLMProvider:
    # Ollama's OpenAI-compatible endpoint ignores the key but the client requires one.
    # Local models here are text-only; image and speech features degrade rather than fail.
    return OpenAICompatibleProvider(
        name="ollama",
        base_url=settings.ollama_base_url,
        api_key="ollama",
        chat_model=settings.ollama_chat_model,
        capabilities=frozenset({Capability.TEXT}),
        default_temperature=settings.temperature,
        default_max_tokens=settings.max_tokens,
        timeout=settings.request_timeout_seconds,
    )


_BUILDERS = {"groq": _build_groq, "ollama": _build_ollama}


@lru_cache
def get_provider() -> LLMProvider:
    settings = get_settings()
    return _BUILDERS[settings.llm_provider](settings)
