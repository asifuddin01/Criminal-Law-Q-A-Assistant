"""Public API routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app import __version__
from app.config import get_settings
from app.legal import DISCLAIMER, SOURCE_ATTRIBUTION
from app.llm import get_provider
from app.schemas import HealthResponse, MetaResponse, ProviderInfo

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """Liveness probe. Deliberately does not touch the model provider, so that a
    provider outage does not read as the service being down."""
    settings = get_settings()
    return HealthResponse(
        status="ok", environment=settings.environment, version=__version__
    )


@router.get("/meta", response_model=MetaResponse, tags=["system"])
async def meta(
    probe: bool = Query(
        default=False,
        description="Probe the provider for live reachability. Costs one model call.",
    ),
) -> MetaResponse:
    """Describe the running system, including which input modalities are available."""
    settings = get_settings()

    try:
        provider = get_provider()
        info = ProviderInfo(
            name=provider.name,
            chat_model=getattr(provider, "_chat_model", "unknown"),
            capabilities=sorted(c.value for c in provider.capabilities),
            reachable=await provider.health() if probe else None,
        )
    except RuntimeError as exc:
        # Misconfiguration must be visible rather than fatal: the service should
        # start and say what is wrong, not refuse to boot.
        info = ProviderInfo(
            name=settings.llm_provider,
            chat_model="unconfigured",
            capabilities=[],
            reachable=False,
        )
        info.model_config.get("extra")
        _ = exc

    return MetaResponse(
        app_name=settings.app_name,
        version=__version__,
        provider=info,
        disclaimer=DISCLAIMER,
        source_attribution=SOURCE_ATTRIBUTION,
    )
