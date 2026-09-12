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
import re
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


# The per-day allowance, which is a different thing from the per-minute one and
# calls for the opposite response: a per-minute limit is waited out inside a run,
# a per-day one cannot be. Defined here rather than in each caller — the
# evaluation harness and the API both have to recognise it, and a second copy is
# a second thing to forget to update.
_DAILY = ("tokens per day", "tpd", "requests per day", "rpd")

_RETRY_AFTER = re.compile(r"try again in ([0-9hms.]+)")


def is_daily_limit(message: str) -> bool:
    """Whether a provider error is the daily allowance rather than the per-minute one."""
    lowered = (message or "").lower()
    return any(marker in lowered for marker in _DAILY)


def retry_delay(message: str, *, default: float = 600.0, cap: float = 1800.0) -> float:
    """Seconds to wait before resuming, taken from the provider's own advice.

    The daily allowance refills continuously rather than resetting at a fixed
    hour, so the provider's retry-after is a real estimate of when the next
    request fits, not a placeholder.
    """
    match = _RETRY_AFTER.search(message or "")
    if not match:
        return default
    text, seconds = match.group(1), 0.0
    for value, unit in re.findall(r"([0-9.]+)([hms])", text):
        seconds += float(value) * {"h": 3600, "m": 60, "s": 1}[unit]
    return min(cap, max(30.0, seconds + 15.0))


def reset_hint(message: str) -> str:
    """How long until the allowance frees up, phrased for a reader."""
    seconds = retry_delay(message, default=0.0)
    if seconds <= 0:
        return ""
    hours, minutes = divmod(int(seconds) // 60, 60)
    if hours:
        return f"about {hours}h {minutes}m"
    return f"about {max(1, minutes)} minutes"
