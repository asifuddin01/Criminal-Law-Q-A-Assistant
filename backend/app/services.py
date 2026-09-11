"""Long-lived application resources.

The corpus, the index and the embedding model are expensive to construct and cheap
to reuse. They are built once at startup and reached through cached accessors rather
than resolved per request — the reason ADR 0008 accepted FastAPI's per-request
dependency injection rather than being constrained by it.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.ingest import (
    Act,
    ScheduleEntry,
    cache_path,
    parse_act,
    parse_schedule,
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
def get_schedule() -> list[ScheduleEntry]:
    source = schedule_path()
    if not source.exists():
        raise CorpusUnavailable(
            "Schedule II not ingested; run: python -m app.ingest --schedule"
        )
    return parse_schedule(source)


@lru_cache(maxsize=1)
def get_lookup() -> ScheduleLookup:
    return ScheduleLookup(get_schedule())


@lru_cache(maxsize=1)
def get_qa() -> RetrievalQA:
    return RetrievalQA(
        get_provider(),
        get_index(),
        name="rag-legal-chunks",
        k=get_settings().retrieval_k,
        lookup=get_lookup(),
    )


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
