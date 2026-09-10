"""Client-side token pacing.

The free tier caps tokens per minute, not requests: 8,000 TPM against 1,000 RPM. A
single evaluation sweep with retrieval context runs into that within a minute, and
retry-with-backoff does not help — the budget is genuinely exhausted, so retries burn
their attempts and the run loses whole slices of the dataset rather than random
questions. That is worse than losing more: a slice missing entirely biases every rate
computed from what remains.

Pacing to stay under the limit turns a failing run into a slow one.
"""

from __future__ import annotations

import asyncio
import time


def estimate_tokens(text: str) -> int:
    """Rough prompt-token estimate. English averages near four characters per token;
    Bengali script runs shorter, so this over-estimates there, which is the safe
    direction for a budget."""
    return max(1, len(text) // 4)


class TokenBucket:
    """Continuously refilling budget of tokens per minute.

    Reservations are made on an estimate before the request and reconciled against
    reported usage afterwards, because a request's true cost is not known until it
    returns. Under-estimating would overrun the limit; over-estimating only slows
    the run, so the reconciliation returns unused budget rather than withholding it.
    """

    def __init__(self, tokens_per_minute: int, *, safety: float = 0.9) -> None:
        self.capacity = max(1.0, tokens_per_minute * safety)
        self._rate = self.capacity / 60.0
        self._available = self.capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        self._available = min(
            self.capacity, self._available + (now - self._updated) * self._rate
        )
        self._updated = now

    async def acquire(self, estimated: int) -> int:
        """Wait until `estimated` tokens of budget are available, then reserve them."""
        want = float(min(estimated, self.capacity))
        while True:
            async with self._lock:
                self._refill()
                if self._available >= want:
                    self._available -= want
                    return int(want)
                shortfall = want - self._available
            await asyncio.sleep(max(0.05, shortfall / self._rate))

    async def reconcile(self, reserved: int, actual: int) -> None:
        """Return over-reserved budget, or charge for an under-estimate."""
        async with self._lock:
            self._refill()
            self._available = max(
                0.0, min(self.capacity, self._available + (reserved - actual))
            )
