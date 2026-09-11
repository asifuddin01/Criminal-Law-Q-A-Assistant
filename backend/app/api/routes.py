"""Public API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app import __version__
from app.config import get_settings
from app.legal import DISCLAIMER, SOURCE_ATTRIBUTION
from app.llm import ProviderUnavailable, get_provider
from app.qa.translate import NOTICE, UnsupportedLanguage, translate
from app.qa.validation import validate
from app.schemas import (
    AskRequest,
    AskResponse,
    CitationOut,
    DroppedCitation,
    HealthResponse,
    MetaResponse,
    ProviderInfo,
    TranslateRequest,
    TranslateResponse,
)
from app.services import CorpusUnavailable, get_corpus, get_qa

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


@router.post("/ask", response_model=AskResponse, tags=["qa"])
async def ask(request: AskRequest) -> AskResponse:
    """Answer a question from retrieved statutory text.

    The answer passes through citation validation before it is returned. Citations
    the validator cannot substantiate are removed and reported in
    `dropped_citations` rather than silently dropped, and an answer left with
    nothing substantiated behind it becomes a refusal.
    """
    try:
        corpus = get_corpus()
        system = get_qa()
    except CorpusUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        answer = await system.answer(request.question)
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=502, detail=f"language model unavailable: {exc}"
        ) from exc

    if answer.error:
        raise HTTPException(status_code=502, detail=answer.error)

    result = validate(answer, corpus, retrieved_sections=answer.retrieved_sections)

    return AskResponse(
        question_text=request.question,
        answer=(
            answer.text
            if not result.refused
            else (answer.text or result.reason)
        ),
        refused=result.refused,
        reason=result.reason,
        citations=[
            CitationOut(
                section=c.section,
                marginal_note=c.marginal_note,
                part=c.part,
                chapter=c.chapter,
                quote=c.quote,
                quote_verified=c.quote_verified,
                source_url=c.source_url,
            )
            for c in result.citations
        ],
        dropped_citations=[DroppedCitation(**d) for d in result.dropped],
        retrieved_sections=answer.retrieved_sections,
        model=answer.model,
        disclaimer=DISCLAIMER,
    )


@router.post("/translate", response_model=TranslateResponse, tags=["qa"])
async def translate_answer(request: TranslateRequest) -> TranslateResponse:
    """Translate an answer's explanation into Bangla or English.

    Offered on demand rather than applied automatically: it costs a second model
    call, and most readers of an English answer do not want one.

    Statutory excerpts are not translated here and are not accepted by this
    endpoint. They are shown with a claim that they were verified verbatim against
    the source, and translating them would leave that claim asserting something
    untrue.
    """
    try:
        translated = await translate(
            request.text, target=request.target, provider=get_provider()
        )
    except UnsupportedLanguage as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=502, detail=f"language model unavailable: {exc}"
        ) from exc

    return TranslateResponse(
        text=translated,
        target=request.target,
        model=getattr(get_provider(), "_chat_model", ""),
        notice=NOTICE.get(request.target, NOTICE["en"]),
    )
