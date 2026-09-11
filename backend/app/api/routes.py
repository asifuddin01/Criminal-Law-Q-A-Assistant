"""Public API routes."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from app import __version__
from app.api.limits import AnswerCache, SlidingWindowLimiter, caller_key
from app.config import get_settings
from app.legal import DISCLAIMER, SOURCE_ATTRIBUTION
from app.llm import Capability, CapabilityUnavailable, ProviderUnavailable, get_provider
from app.qa import ocr
from app.qa.documents import DocumentStore, UnreadableDocument
from app.qa.translate import NOTICE, UnsupportedLanguage, translate
from app.qa.validation import validate
from app.schemas import (
    AmendmentOut,
    AskRequest,
    AskResponse,
    CitationOut,
    DocumentResponse,
    DroppedCitation,
    HealthResponse,
    ImageTextResponse,
    MetaResponse,
    ProviderInfo,
    TranscriptionResponse,
    TranslateRequest,
    TranslateResponse,
)
from app.services import CorpusUnavailable, get_corpora, get_qa, get_schedule

router = APIRouter()

_settings = get_settings()
_limiter = SlidingWindowLimiter(_settings.rate_limit_per_hour)
_answers = AnswerCache(_settings.answer_cache_size)
_documents = DocumentStore()

UPLOAD_NOTICE = (
    "This document is not part of the legal corpus and carries no authority. It is "
    "used only to answer questions that reference it, is never cited as law, and is "
    "held in memory rather than stored."
)


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

    features = ["text", "upload"]
    if "transcription" in info.capabilities:
        features.append("speech")
    if ocr.available():
        features.append("image")

    return MetaResponse(
        app_name=settings.app_name,
        version=__version__,
        provider=info,
        features=sorted(features),
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
    # Resolved before anything expensive: a document that is gone should say so
    # whatever else is misconfigured, and loading the corpus first would report the
    # wrong problem.
    extra_chunks = []
    if request.document_id:
        document = _documents.get(request.document_id)
        if document is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "that document is not available — uploads are held in memory "
                    "and are lost when the service restarts. Upload it again."
                ),
            )
        extra_chunks = document.chunks()

    try:
        corpora = get_corpora()
        schedule = get_schedule()
        system = get_qa()
    except CorpusUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        # A provider that cannot be constructed — no credential, usually. The same
        # reasoning as /meta: report the misconfiguration rather than failing as an
        # unexplained server error.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Cache first. A repeat question costs nothing, so it should not consume an
    # allowance either — the limit exists to protect the token budget, and a cache
    # hit spends none of it.
    cache_key = _answers.key(
        request.question,
        model=system.model_name,
        index=f"{system.index_name}|{system.fingerprint}|{request.document_id or ''}",
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
        answer = await system.answer(request.question, extra_chunks=extra_chunks)
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
        corpora,
        schedule=schedule,
        uploaded={c.section_number: c.text for c in extra_chunks},
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
                amendments=[AmendmentOut(**asdict(a)) for a in c.amendments],
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


@router.post("/documents", response_model=DocumentResponse, tags=["qa"])
async def upload_document(
    file: Annotated[UploadFile, File(description="A PDF or plain text file")],
) -> DocumentResponse:
    """Accept a document to ask questions against.

    This does not add anything to the legal corpus. Adding an act is an ingestion
    step run against a published source, not something a visitor can do by uploading
    a file — a system that let anyone add text and then cited it as law would have no
    grounding worth the name.

    Text is extracted, not OCR'd, so a scanned PDF with no text layer is refused with
    that explanation rather than accepted and silently empty.
    """
    payload = await file.read()
    try:
        document = _documents.add(
            payload,
            filename=file.filename or "document",
            media_type=file.content_type or "",
        )
    except UnreadableDocument as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return DocumentResponse(
        document_id=document.document_id,
        filename=document.filename,
        pages=document.pages,
        characters=document.characters,
        preview=document.preview(),
        notice=UPLOAD_NOTICE,
    )


@router.post("/image", response_model=ImageTextResponse, tags=["qa"])
async def read_image(
    http_request: Request,
    image: Annotated[UploadFile, File(description="A photograph of a document")],
) -> ImageTextResponse:
    """Read the text out of a photographed document.

    Served by OCR rather than a vision model, because the provider catalogue offers
    none — and because for a photograph of legal paper the wanted output is the text
    exactly as written. A vision model paraphrases; OCR transcribes, which is the
    right primitive for a system whose claim is verbatim grounding.

    The text is returned for the user to check, not answered directly.
    """
    payload = await image.read()

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

    languages = ocr.language_argument()
    started = time.perf_counter()
    try:
        text = ocr.read_image(payload, languages=languages)
    except ocr.OCRUnavailable as exc:
        _limiter.forget(caller)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ocr.UnreadableImage as exc:
        _limiter.forget(caller)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ImageTextResponse(
        text=text,
        languages=languages,
        seconds=round(time.perf_counter() - started, 2),
    )
