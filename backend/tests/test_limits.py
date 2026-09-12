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
