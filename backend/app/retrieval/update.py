"""Incremental corpus update.

    python -m app.retrieval.update --index legal_aware_schedule

The index converges on whatever sources are present in `data/raw`. Adding an act,
replacing one with a newer consolidation, and removing one are therefore the same
operation: re-derive the chunks every source implies, and let the index work out what
actually changed.

Only new or altered chunks are embedded. That is the point — a corpus that must be
rebuilt in full to gain one act is a corpus nobody updates.
"""

from __future__ import annotations

import argparse
import sys

from app.ingest import (
    act_print_url,
    parse_act,
    parse_schedule,
    schedule_path,
)
from app.ingest.fetch import RAW_DIR
from app.retrieval.chunking import Chunk, legal_aware, schedule_rows
from app.retrieval.index import VectorIndex


def ingested_acts() -> list[int]:
    """Act ids present in the raw cache, in ascending order."""
    ids = []
    for path in RAW_DIR.glob("act-print-*.html"):
        stem = path.stem.removeprefix("act-print-")
        if stem.isdigit():
            ids.append(int(stem))
    return sorted(ids)


def desired_chunks() -> tuple[list[Chunk], list[str]]:
    """Every chunk the ingested sources imply, with a description of each source."""
    chunks: list[Chunk] = []
    sources: list[str] = []

    for act_id in ingested_acts():
        path = RAW_DIR / f"act-print-{act_id}.html"
        act = parse_act(
            path.read_text(encoding="utf-8", errors="replace"),
            act_id=act_id,
            source_url=act_print_url(act_id),
        )
        act_chunks = legal_aware(act)
        chunks.extend(act_chunks)
        sources.append(f"act-{act_id} {act.title} — {len(act_chunks)} chunks")

    if schedule_path().exists():
        rows = schedule_rows(parse_schedule(schedule_path()))
        chunks.extend(rows)
        sources.append(f"Schedule II — {len(rows)} chunks")

    return chunks, sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update a retrieval index in place.")
    parser.add_argument("--index", default="legal_aware_schedule")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without embedding or saving",
    )
    args = parser.parse_args(argv)

    if not VectorIndex.exists(args.index):
        print(
            f"index {args.index!r} does not exist; build it first:\n"
            f"  python -m app.retrieval.build --strategy legal_aware --with-schedule"
        )
        return 2

    index = VectorIndex.load(args.index)
    before = len(index)
    chunks, sources = desired_chunks()

    print(f"index {args.index}: {before} chunks")
    for source in sources:
        print(f"  source: {source}")

    if args.dry_run:
        have = {c.chunk_id: c.content_hash for c in index.chunks}
        want = {c.chunk_id: c.content_hash for c in chunks}
        added = len(want.keys() - have.keys())
        removed = len(have.keys() - want.keys())
        changed = sum(
            1 for k in want.keys() & have.keys() if want[k] != have[k]
        )
        print(
            f"would embed {added + changed} chunks "
            f"({added} added, {changed} changed), remove {removed}"
        )
        return 0

    result = index.update(chunks)
    index.save(args.index)

    print(result.summary())
    print(f"index {args.index}: {before} -> {len(index)} chunks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
