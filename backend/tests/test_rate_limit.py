"""Token bucket tests."""

from __future__ import annotations

import asyncio
import time

from app.llm.rate_limit import TokenBucket, estimate_tokens


def test_capacity_holds_back_a_safety_margin():
    assert TokenBucket(8000, safety=0.9).capacity == 7200.0


async def test_a_reservation_within_budget_does_not_wait():
    bucket = TokenBucket(8000)

    started = time.monotonic()
    await bucket.acquire(1000)

    assert time.monotonic() - started < 0.05


async def test_a_reservation_beyond_budget_waits_for_refill():
    """The point of the bucket: exceed the budget and the caller is delayed rather
    than sent into a 429 it cannot retry its way out of."""
    bucket = TokenBucket(6000)  # 5400 capacity, 90/second refill
    await bucket.acquire(5400)

    started = time.monotonic()
    await bucket.acquire(90)
    waited = time.monotonic() - started

    assert 0.4 < waited < 3.0


async def test_reconciliation_returns_unused_budget():
    bucket = TokenBucket(8000)
    await bucket.acquire(5000)

    await bucket.reconcile(reserved=5000, actual=1000)

    # 4000 returned, so a further large reservation succeeds immediately.
    started = time.monotonic()
    await bucket.acquire(4000)
    assert time.monotonic() - started < 0.05


async def test_reconciliation_charges_for_an_underestimate():
    bucket = TokenBucket(6000)
    await bucket.acquire(100)

    await bucket.reconcile(reserved=100, actual=5400)

    started = time.monotonic()
    await bucket.acquire(500)
    assert time.monotonic() - started > 0.2


async def test_a_reservation_larger_than_capacity_is_clamped_not_deadlocked():
    """A single request bigger than the whole budget must still go through, or the
    run stops forever on one long prompt."""
    bucket = TokenBucket(600)

    await asyncio.wait_for(bucket.acquire(10_000), timeout=5)


def test_token_estimate_scales_with_length():
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 100
