"""Rate limiting and answer caching.

These exist to keep a public demo alive on a free-tier token allowance, so the
behaviour that matters is which requests actually cost budget.
"""

from __future__ import annotations

from app.api.limits import AnswerCache, SlidingWindowLimiter, caller_key


def test_allowance_is_spent_then_refused():
    limiter = SlidingWindowLimiter(limit=3)

    assert [limiter.check("a").allowed for _ in range(3)] == [True, True, True]

    refused = limiter.check("a")
    assert refused.allowed is False
    assert refused.remaining == 0
    assert refused.retry_after > 0


def test_callers_are_limited_independently():
    limiter = SlidingWindowLimiter(limit=1)

    assert limiter.check("a").allowed is True
    assert limiter.check("b").allowed is True
    assert limiter.check("a").allowed is False


def test_a_zero_limit_disables_limiting():
    """Local development should not be rate limited by default."""
    limiter = SlidingWindowLimiter(limit=0)

    assert all(limiter.check("a").allowed for _ in range(50))


def test_forget_returns_an_allowance():
    """A request that failed before reaching the provider cost no budget, so it
    must not cost the caller an allowance either."""
    limiter = SlidingWindowLimiter(limit=1)
    limiter.check("a")

    limiter.forget("a")

    assert limiter.check("a").allowed is True


def test_remaining_counts_down():
    limiter = SlidingWindowLimiter(limit=3)

    assert [limiter.check("a").remaining for _ in range(3)] == [2, 1, 0]


def test_cache_key_ignores_case_and_whitespace():
    """The same question typed differently is the same question."""
    args = {"model": "m", "index": "i"}
    a = AnswerCache.key("When may police arrest?", **args)
    b = AnswerCache.key("  when   MAY police arrest? ", **args)

    assert a == b


def test_cache_key_separates_models_and_indexes():
    """An answer cached under one configuration must never be served under
    another: it would report text the system no longer retrieves."""
    base = AnswerCache.key("q", model="a", index="i")

    assert AnswerCache.key("q", model="b", index="i") != base
    assert AnswerCache.key("q", model="a", index="j") != base


def test_cache_returns_what_was_stored_and_counts_hits():
    cache = AnswerCache(capacity=4)
    key = AnswerCache.key("q", model="m", index="i")

    assert cache.get(key) is None
    cache.put(key, "answer")

    assert cache.get(key) == "answer"
    assert (cache.hits, cache.misses) == (1, 1)


def test_cache_evicts_least_recently_used():
    cache = AnswerCache(capacity=2)
    for name in ("a", "b"):
        cache.put(name, name)

    cache.get("a")        # 'a' becomes most recent, so 'b' is next out
    cache.put("c", "c")

    assert cache.get("b") is None
    assert cache.get("a") == "a"
    assert len(cache) == 2


def test_forwarded_header_identifies_the_caller_behind_a_proxy():
    assert caller_key("10.0.0.1", "203.0.113.7, 10.0.0.1") == "203.0.113.7"
    assert caller_key("10.0.0.1", None) == "10.0.0.1"
    assert caller_key(None, None) == "unknown"


def test_the_local_provider_gets_a_longer_timeout_than_the_hosted_one():
    """Regression. One timeout for both measured the machine, not the system.

    At 60 seconds a full sweep lost five questions to timeouts, four of them in
    the Bangla slice — the one that generates the most tokens per character with
    this tokenizer. An errored question is excluded from the rates, so the effect
    was not a visible "slow" but a Bangla slice quietly measured over fewer
    questions than every other slice.
    """
    from app.config import Settings

    settings = Settings()

    assert settings.ollama_timeout_seconds > settings.request_timeout_seconds


def test_a_spent_daily_allowance_reads_as_a_limit_not_a_crash():
    """The one failure a shared deployment actually hits.

    Left raw it reaches the page as "502: Error code: 429 - ... TPD ...", which a
    reviewer reads as a broken application rather than a spent free-tier quota.
    """
    from app.api.routes import _provider_error

    daily = _provider_error(
        "Error code: 429 - Rate limit reached for model gpt-oss-120b: Limit 200000, "
        "Used 199900. Please try again in 12m30s. tokens per day (TPD)"
    )

    assert daily.status_code == 503
    assert "daily token allowance" in daily.detail
    assert "12 minutes" in daily.detail
    # It says what still works, because everything except the model call does.
    assert "citation checks" in daily.detail


def test_an_unreachable_model_is_a_503_and_an_unexpected_one_is_a_502():
    """The two are different things and a client can act differently on them.

    Unreachable is temporary and worth retrying; an upstream that answered with
    something unexpected is not.
    """
    from app.api.routes import _provider_error

    unreachable = _provider_error("connection reset by peer")
    assert unreachable.status_code == 503
    assert "connection reset" in unreachable.detail

    unexpected = _provider_error("model returned an unparseable response")
    assert unexpected.status_code == 502
    assert "unparseable" in unexpected.detail


def test_the_embedding_cache_location_can_be_set(monkeypatch, tmp_path):
    """Regression, found while writing the container and before it shipped.

    fastembed caches the model under the system temp path when nothing says
    otherwise. That is invisible on a laptop and wrong in a container: a host
    that hands the process a fresh /tmp re-downloads 120 MB on every cold start,
    and the first question anyone asks pays for it. The image warms the cache at
    build time, so both sides have to name the same directory.
    """
    from app.config import Settings, get_settings

    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path / "models"))
    get_settings.cache_clear()
    try:
        assert get_settings().embedding_cache_dir == str(tmp_path / "models")
    finally:
        get_settings.cache_clear()

    # Unset, fastembed keeps its own default rather than being handed "".
    monkeypatch.delenv("EMBEDDING_CACHE_DIR")
    assert Settings(_env_file=None).embedding_cache_dir == ""


def test_settings_load_with_no_environment_at_all():
    """The image warms the model at build time, where no credential exists.

    A required setting without a default would fail the build with an error about
    a missing API key, in a step that does not use one.
    """
    from app.config import Settings

    assert Settings(_env_file=None).app_name


def test_a_truncated_reply_is_reported_as_truncation_not_as_a_missing_citation():
    """Regression, found on the deployed Space rather than in a test.

    The hosted model hit its token budget mid-sentence. The JSON never closed,
    so the reply parsed as prose, produced no citations, and the validation gate
    withheld it with "No citation in the answer could be verified against the
    retrieved statutory text" — a message that blames the model's grounding for
    a budget that ran out, shown to a user who cannot tell the difference.
    """
    import asyncio

    from app.llm.base import ChatMessage, Completion
    from app.qa.rag import RetrievalQA

    class TruncatingProvider:
        name = "stub"
        _chat_model = "stub-model"

        async def complete(self, messages: list[ChatMessage], **kwargs) -> Completion:
            return Completion(
                text='{"refused": false, "answer": "A police-officer may arrest',
                model="stub-model",
                completion_tokens=2500,
                finish_reason="length",
            )

    class OneChunkIndex:
        model_name = "stub-embeddings"
        chunks: list = []

        def search(self, query: str, *, k: int = 10):
            from app.retrieval.chunking import Chunk

            chunk = Chunk(
                chunk_id="legal-CrPC-54-0",
                text="54. (1) Any police-officer may arrest without warrant.",
                section_number="54",
                marginal_note="When police may arrest without warrant",
                part=None,
                chapter=None,
                strategy="legal_aware",
            )

            class Hit:
                pass

            hit = Hit()
            hit.chunk = chunk
            return [hit]

        def __len__(self) -> int:
            return 1

    system = RetrievalQA(TruncatingProvider(), OneChunkIndex(), name="test")
    answer = asyncio.run(system.answer("When may a police officer arrest?"))

    assert answer.error is not None
    assert "token budget" in answer.error
    assert "2500" in answer.error
    # And it is an error, not a refusal dressed up as one.
    assert answer.refused is False


def test_the_answer_budget_covers_a_reasoning_model():
    """2500 truncated the hosted model on ordinary questions."""
    from app.config import Settings

    assert Settings(_env_file=None).answer_max_tokens >= 4000
