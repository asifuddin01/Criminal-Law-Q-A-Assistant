"""Public API routes."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from app import __version__
from app.api.limits import AnswerCache, SlidingWindowLimiter, caller_key
from app.config import get_settings
from app.legal import DISCLAIMER, SOURCE_ATTRIBUTION
from app.llm import Capability, CapabilityUnavailable, ProviderUnavailable, get_provider
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
    TranscriptionResponse,
    TranslateRequest,
    TranslateResponse,
)
from app.services import CorpusUnavailable, get_corpus, get_qa, get_schedule

router = APIRouter()

_settings = get_settings()
_limiter = SlidingWindowLimiter(_settings.rate_limit_per_hour)
_answers = AnswerCache(_settings.answer_cache_size)


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
async def ask(request: AskRequest, http_request: Request) -> AskResponse:
    """Answer a question from retrieved statutory text.

    The answer passes through citation validation before it is returned. Citations
    the validator cannot substantiate are removed and reported in
    `dropped_citations` rather than silently dropped, and an answer left with
    nothing substantiated behind it becomes a refusal.
    """
    try:
        corpus = get_corpus()
        schedule = get_schedule()
        system = get_qa()
    except CorpusUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Cache first. A repeat question costs nothing, so it should not consume an
    # allowance either — the limit exists to protect the token budget, and a cache
    # hit spends none of it.
    cache_key = _answers.key(
        request.question, model=system.model_name, index=system.index_name
    )
    cached = _answers.get(cache_key)
    if cached is not None:
        return cached.model_copy(update={"cached": True})

    caller = caller_key(
        http_request.client.host if http_request.client else None,
        http_request.headers.get("x-forwarded-for"),
    )
    decision = _limiter.check(caller)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Question limit reached. This demo shares one free-tier token "
                f"allowance across all visitors, so each caller gets "
                f"{_limiter.limit} questions an hour. Try again in "
                f"{decision.retry_after / 60:.0f} minutes."
            ),
            headers={"Retry-After": str(int(decision.retry_after) + 1)},
        )

    try:
        answer = await system.answer(request.question)
    except ProviderUnavailable as exc:
        # The request cost nothing, so it should not cost an allowance either.
        _limiter.forget(caller)
        raise HTTPException(
            status_code=502, detail=f"language model unavailable: {exc}"
        ) from exc

    if answer.error:
        _limiter.forget(caller)
        raise HTTPException(status_code=502, detail=answer.error)

    result = validate(
        answer,
        corpus,
        schedule=schedule,
        retrieved_sections=answer.retrieved_sections,
    )

    response = AskResponse(
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
                source=c.source,
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
    _answers.put(cache_key, response)
    return response


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


# Whisper accepts 25 MB. Rejecting oversized uploads here keeps a long upload from
# being spent before the provider refuses it.
MAX_AUDIO_BYTES = 25 * 1024 * 1024

AUDIO_SUFFIXES = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/flac": "flac",
}


@router.post("/transcribe", response_model=TranscriptionResponse, tags=["qa"])
async def transcribe(
    http_request: Request,
    audio: Annotated[UploadFile, File(description="Recorded question")],
    language: Annotated[
        str | None,
        Form(description="ISO hint such as 'bn'. Omit to let the model detect it."),
    ] = None,
) -> TranscriptionResponse:
    """Convert a spoken question to text.

    Returns the text rather than answering it, so the caller can see what was heard.
    See ADR 0004: modality is erased at this boundary, and everything downstream is
    the ordinary text path.
    """
    provider = get_provider()
    if not provider.supports(Capability.TRANSCRIPTION):
        raise HTTPException(
            status_code=503,
            detail=(
                f"The configured provider ({provider.name}) has no transcription "
                "model, so speech input is unavailable in this deployment."
            ),
        )

    payload = await audio.read()
    if not payload:
        raise HTTPException(status_code=422, detail="the uploaded audio was empty")
    if len(payload) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"audio is {len(payload) / 1_048_576:.1f} MB; the limit is "
                f"{MAX_AUDIO_BYTES // 1_048_576} MB"
            ),
        )

    caller = caller_key(
        http_request.client.host if http_request.client else None,
        http_request.headers.get("x-forwarded-for"),
    )
    decision = _limiter.check(caller)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Request limit reached. Try again in "
                f"{decision.retry_after / 60:.0f} minutes."
            ),
            headers={"Retry-After": str(int(decision.retry_after) + 1)},
        )

    # Whisper infers the format from the filename, and a browser recording arrives
    # as a blob with no useful name.
    suffix = AUDIO_SUFFIXES.get((audio.content_type or "").split(";")[0], "webm")
    started = time.perf_counter()
    try:
        text = await provider.transcribe(
            payload, f"question.{suffix}", language=language
        )
    except CapabilityUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderUnavailable as exc:
        _limiter.forget(caller)
        raise HTTPException(
            status_code=502, detail=f"transcription unavailable: {exc}"
        ) from exc

    if not text.strip():
        _limiter.forget(caller)
        raise HTTPException(
            status_code=422,
            detail="nothing was recognised in the recording",
        )

    return TranscriptionResponse(
        text=text,
        language=language,
        model=getattr(provider, "_transcription_model", ""),
        seconds=round(time.perf_counter() - started, 2),
    )
