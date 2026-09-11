"""Request limiting for a publicly reachable demo.

The provider's free tier allows roughly 200,000 tokens a day, and a grounded answer
costs about 2,500. That is some eighty questions a day for every visitor combined. A
public link shared anywhere is exhausted by a handful of curious strangers, and then
the demo shows errors to whoever actually needed to see it work.

Two measures, in this order:

  - repeat questions are served from cache and cost nothing. Generation runs at
    temperature zero, so the same question already produces the same answer; serving
    it from cache changes what it costs, not what it says.
  - each caller gets a small allowance per hour.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict, deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    remaining: int
    retry_after: float = 0.0


class SlidingWindowLimiter:
    """A fixed allowance per caller over a rolling window.

    Deliberately in-process and in-memory. A demo runs as one container, and a
    shared store would be a dependency added for a problem this does not have.
    Restarting clears the allowances, which is acceptable for a demo and is stated
    rather than hidden.
    """

    def __init__(self, limit: int, window_seconds: float = 3600.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits.setdefault(key, deque())
        cutoff = now - self.window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return hits

    def check(self, key: str) -> Decision:
        """Record an attempt and say whether it is allowed."""
        if self.limit <= 0:
            return Decision(allowed=True, remaining=-1)

        now = time.monotonic()
        hits = self._prune(key, now)

        if len(hits) >= self.limit:
            return Decision(
                allowed=False,
                remaining=0,
                retry_after=max(0.0, hits[0] + self.window - now),
            )

        hits.append(now)
        return Decision(allowed=True, remaining=self.limit - len(hits))

    def forget(self, key: str) -> None:
        """Return an allowance, for a request that ended up costing nothing."""
        hits = self._hits.get(key)
        if hits:
            hits.pop()


class AnswerCache:
    """Bounded cache of answers, keyed on the question.

    Keys include the model and index so a cached answer is never served from a
    configuration that no longer exists — a stale answer attributed to the current
    system would be a quiet lie about what the system does.
    """

    def __init__(self, capacity: int = 512) -> None:
        self.capacity = capacity
        self._entries: OrderedDict[str, object] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(question: str, *, model: str, index: str) -> str:
        normalized = " ".join(question.split()).casefold()
        digest = f"{model}\x00{index}\x00{normalized}"
        return hashlib.sha256(digest.encode("utf-8")).hexdigest()

    def get(self, key: str):
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        self._entries.move_to_end(key)
        self.hits += 1
        return entry

    def put(self, key: str, value: object) -> None:
        self._entries[key] = value
        self._entries.move_to_end(key)
        while len(self._entries) > self.capacity:
            self._entries.popitem(last=False)

    def __len__(self) -> int:
        return len(self._entries)


def caller_key(client_host: str | None, forwarded_for: str | None) -> str:
    """Identify a caller.

    Behind a proxy the socket address is the proxy, so the forwarded header is used
    when present. It is client-supplied and therefore spoofable — acceptable for
    protecting a demo's token budget, and not something to reuse for anything that
    matters.
    """
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return client_host or "unknown"
