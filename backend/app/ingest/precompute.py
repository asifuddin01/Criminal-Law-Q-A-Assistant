"""Precompute the parsed Schedule II.

    python -m app.ingest.precompute

Parsing the 161-page Schedule II PDF takes 48 seconds and yields the same 376
rows every time. On a laptop that is a one-off annoyance; on a deployment that
sleeps when idle it is 81% of a cold start, paid again on every wake, before the
first page is served.

The PDF is a fixed input and the parse is deterministic, so it is done once — at
image build time — and the result read back in milliseconds. The PDF still ships,
because it is the provenance for what this file contains.
"""

from __future__ import annotations

import sys
import time

from app.ingest import dump_entries, parse_schedule, parsed_schedule_path, schedule_path


def main() -> int:
    source = schedule_path()
    if not source.exists():
        print(f"Schedule II not fetched: {source}")
        print("run: python -m app.ingest --schedule")
        return 2

    started = time.perf_counter()
    entries = parse_schedule(source)
    elapsed = time.perf_counter() - started

    destination = dump_entries(entries, parsed_schedule_path())
    size = destination.stat().st_size / 1024
    print(f"parsed {len(entries)} rows in {elapsed:.1f}s -> {destination} ({size:.0f} KB)")
    print("startup reads this instead of re-parsing the PDF")
    return 0


if __name__ == "__main__":
    sys.exit(main())
