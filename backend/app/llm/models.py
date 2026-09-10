"""List the model catalogue the configured provider actually offers.

    python -m app.llm.models

Model identifiers change without notice and differ between accounts. Hardcoding one
from memory produces a service that authenticates successfully and then fails every
request, which reads as a credential problem and is not one.
"""

from __future__ import annotations

import asyncio
import sys

from openai import AsyncOpenAI

from app.config import get_settings


async def _list() -> int:
    settings = get_settings()
    if settings.llm_provider == "groq":
        base_url, api_key = settings.groq_base_url, settings.groq_api_key
    else:
        base_url, api_key = settings.ollama_base_url, "ollama"

    if not api_key:
        print(f"no credential configured for provider {settings.llm_provider!r}")
        return 1

    client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=30)
    catalogue = await client.models.list()
    identifiers = sorted(model.id for model in catalogue.data)

    print(f"provider: {settings.llm_provider} ({len(identifiers)} models)")
    for identifier in identifiers:
        print(f"  {identifier}")

    print("\nconfigured:")
    for label, configured in (
        ("chat", settings.groq_chat_model),
        ("transcription", settings.groq_transcription_model),
        ("vision", settings.groq_vision_model),
    ):
        if not configured:
            print(f"  {label:<14} (unset — capability not declared)")
        else:
            mark = "ok" if configured in identifiers else "NOT IN CATALOGUE"
            print(f"  {label:<14} {configured}  [{mark}]")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_list()))
