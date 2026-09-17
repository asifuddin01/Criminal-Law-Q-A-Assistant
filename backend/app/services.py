"""Long-lived application resources.

The corpus, the index and the embedding model are expensive to construct and cheap
to reuse. They are built once at startup and reached through cached accessors rather
than resolved per request — the reason ADR 0008 accepted FastAPI's per-request
dependency injection rather than being constrained by it.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from app.config import get_settings
from app.ingest import (
    Act,
    ScheduleEntry,
    cache_path,
    load_entries,
    parse_act,
    parse_schedule,
    parsed_schedule_path,
    schedule_path,
)
from app.llm import get_provider
from app.qa import RetrievalQA
from app.retrieval import ScheduleLookup, VectorIndex

ACT_ID = 75
ACT_URL = f"https://bdlaws.minlaw.gov.bd/act-print-{ACT_ID}.html"

# The strategy the measurements chose. Retrieval-only evaluation put legal-aware
# chunking at recall@10 of 90.3% against 52.8% for fixed-size windows.
INDEX_NAME = "legal_aware_schedule"


class CorpusUnavailable(RuntimeError):
    """The corpus or its index has not been built."""


@lru_cache(maxsize=1)
def get_corpus() -> Act:
    source = cache_path(ACT_ID)
    if not source.exists():
        raise CorpusUnavailable(
            "corpus not ingested; run: python -m app.ingest"
        )
    return parse_act(
        source.read_text(encoding="utf-8", errors="replace"),
        act_id=ACT_ID,
        source_url=ACT_URL,
    )


@lru_cache(maxsize=1)
def get_index() -> VectorIndex:
    if not VectorIndex.exists(INDEX_NAME):
        raise CorpusUnavailable(
            f"index not built; run: python -m app.retrieval.build "
            f"--strategy {INDEX_NAME}"
        )
    return VectorIndex.load(INDEX_NAME)


@lru_cache(maxsize=1)
def get_corpora() -> dict[str, Act]:
    """Every ingested act, keyed by the document code its citations name."""
    from app.retrieval.chunking import document_for

    corpora: dict[str, Act] = {}
    for act_id in (75, 11):
        source = cache_path(act_id)
        if not source.exists():
            continue
        corpora[document_for(act_id)] = parse_act(
            source.read_text(encoding="utf-8", errors="replace"),
            act_id=act_id,
            source_url=f"https://bdlaws.minlaw.gov.bd/act-print-{act_id}.html",
        )
    if not corpora:
        raise CorpusUnavailable("corpus not ingested; run: python -m app.ingest")
    return corpora


@lru_cache(maxsize=1)
def get_schedule() -> list[ScheduleEntry]:
    # The parsed cache first. Parsing the PDF takes 48 seconds and produces the
    # same 376 rows every time; a deployment that sleeps would pay it on every
    # wake, before serving its first page.
    parsed = parsed_schedule_path()
    if parsed.exists():
        return load_entries(parsed)

    source = schedule_path()
    if not source.exists():
        raise CorpusUnavailable(
            "Schedule II not ingested; run: python -m app.ingest --schedule"
        )
    return parse_schedule(source)


@lru_cache(maxsize=1)
def get_lookup() -> ScheduleLookup:
    return ScheduleLookup(get_schedule())


@lru_cache(maxsize=2)
def get_qa(provider: str | None = None) -> RetrievalQA:
    """The answering system, optionally on a named provider.

    The default is the configured one. Naming a provider lets an interface offer
    the choice — a local model is free and unmetered where one is running, which
    is what a spent hosted allowance leaves you. It is cached per provider, so
    switching back and forth does not rebuild the index.
    """
    from app.qa.rag import clarifies

    chosen = get_provider(provider)
    return RetrievalQA(
        chosen,
        get_index(),
        name="rag-legal-chunks",
        k=get_settings().retrieval_k,
        lookup=get_lookup(),
        clarify=clarifies(chosen.name),
    )


def transcription_provider():
    """A provider that can turn speech into text, whichever model answers.

    Transcription is not the answering model's job. ADR 0004 erases modality at
    the API boundary — speech becomes text and everything downstream is the
    ordinary text path — so which model writes the answer has nothing to do with
    what heard the question.

    Binding the two together had a visible cost: selecting the local model, which
    is text-only, made the Speak button disappear from the interface, because the
    deployment was reporting its answering model's capabilities as the whole
    system's. Returns None when nothing configured can transcribe.
    """
    from app.llm import Capability

    settings = get_settings()
    names = [settings.llm_provider] + [
        n for n in ("groq", "ollama") if n != settings.llm_provider
    ]
    for name in names:
        try:
            provider = get_provider(name)
        except Exception:  # noqa: BLE001 — an unconfigured provider is not an error here
            continue
        if provider.supports(Capability.TRANSCRIPTION):
            return provider
    return None


# How this deployment's local model is doing, when the deployment is the thing
# fetching it. Left unset everywhere else, which is the ordinary case: a local
# model is either running on the machine or it is not.
_describe_local: Callable[[], str] | None = None


def describe_local_model(describe: Callable[[], str] | None) -> None:
    """Register a description of the local model's state, shown by /api/meta.

    A Space has no persistent storage, so it downloads 3.3 GB of runtime and
    weights on every cold start and the model is genuinely absent for the first
    few minutes. "No Ollama server is reachable" is true throughout that and
    tells a visitor nothing they can act on — they cannot start one, and the
    honest answer is that it is on its way.

    The deployment knows this; the API does not, and should not have to import a
    Space's downloader to find out. Pass None to clear.
    """
    global _describe_local
    _describe_local = describe


def local_model_note() -> str:
    """What to say about a local model that is not answering yet."""
    if _describe_local is None:
        return ""
    try:
        return _describe_local()
    except Exception:  # noqa: BLE001 — an explanation is not worth an error
        return ""


def local_provider_reachable(timeout: float = 1.5) -> bool:
    """Whether an Ollama server is actually answering, right now.

    Asked rather than assumed. A hosted deployment has no local model — a
    Hugging Face Space cannot run Ollama — and an interface that offers a switch
    to something that is not there is worse than one that offers no switch.
    """
    import httpx

    base = get_settings().ollama_base_url.rstrip("/").removesuffix("/v1")
    try:
        return httpx.get(f"{base}/api/tags", timeout=timeout).status_code == 200
    except Exception:  # noqa: BLE001 — unreachable is the answer, not an error
        return False


def warm() -> dict[str, str]:
    """Build everything at startup so the first request is not the slow one.

    Failures are reported rather than raised: a deployment missing its index should
    start and say so, the same reasoning that keeps /meta alive without a provider.
    """
    status: dict[str, str] = {}
    for name, builder, describe in (
        ("corpus", get_corpus, lambda a: f"{len(a.sections)} sections"),
        ("index", get_index, lambda i: f"{len(i)} chunks"),
        ("schedule", get_schedule, lambda s: f"{len(s)} offences"),
    ):
        try:
            status[name] = describe(builder())
        except CorpusUnavailable as exc:
            status[name] = f"unavailable: {exc}"
    return status
