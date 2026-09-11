"""Incremental corpus update.

    python -m app.retrieval.update --index legal_aware_schedule

The index converges on whatever sources are present in `data/raw`. Adding an act,
replacing one with a newer consolidation, and removing one are therefore the same
operation: re-derive the chunks every source implies, and let the index work out what
actually changed.

Only new or altered chunks are embedded. That is the point — a corpus that must be
rebuilt in full to gain one act is a corpus nobody updates.

*Which* chunks a source implies is read from the index being updated, never assumed.
An index records the chunking strategy each of its chunks was built with and which
documents it holds, and those are what make it the index it is. This file previously
derived the legal-aware chunk set for every index it was pointed at, so updating the
naive-chunk index replaced it with legal-aware chunks and the schedule — silently
turning the two indexes whose difference stages 2 and 3 exist to measure into copies
of the stage 4 corpus. The comparison would have gone on reporting numbers.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from app.ingest import (
    act_print_url,
    parse_act,
    parse_schedule,
    schedule_path,
)
from app.ingest.fetch import RAW_DIR
from app.retrieval.chunking import STRATEGIES, Chunk, document_for, schedule_rows
from app.retrieval.index import VectorIndex

# Above this share of the index added-plus-removed, the operation is a rebuild.
# An update is meant to converge an index on changed sources; one that replaces
# most of it has been pointed at the wrong definition.
REBUILD_THRESHOLD = 0.25


def ingested_acts() -> list[int]:
    """Act ids present in the raw cache, in ascending order."""
    ids = []
    for path in RAW_DIR.glob("act-print-*.html"):
        stem = path.stem.removeprefix("act-print-")
        if stem.isdigit():
            ids.append(int(stem))
    return sorted(ids)


@dataclass(frozen=True, slots=True)
class IndexShape:
    """What an existing index is, read from the index itself."""

    strategy: str
    acts: tuple[int, ...]
    with_schedule: bool

    def describe(self) -> str:
        acts = ", ".join(f"act-{a}" for a in self.acts) or "no acts"
        schedule = " + Schedule II" if self.with_schedule else ""
        return f"{self.strategy} over {acts}{schedule}"


def shape_of(index: VectorIndex) -> IndexShape:
    """Read an index's own definition off its chunks.

    Section chunks carry the strategy they were built with, and every chunk carries
    the document it belongs to. Schedule rows are their own strategy. An index that
    holds more than one section-chunking strategy is not a shape this can update,
    and says so rather than picking one.
    """
    strategies = {
        c.strategy for c in index.chunks if c.strategy != "schedule_rows"
    }
    if len(strategies) > 1:
        raise ValueError(
            f"index mixes chunking strategies {sorted(strategies)}; "
            "rebuild it rather than updating it"
        )
    documents = {c.document for c in index.chunks}
    acts = tuple(
        act_id
        for act_id in ingested_acts()
        if document_for(act_id) in documents
    )
    return IndexShape(
        strategy=strategies.pop() if strategies else "legal_aware",
        acts=acts,
        with_schedule=any(c.strategy == "schedule_rows" for c in index.chunks),
    )


def desired_chunks(shape: IndexShape) -> tuple[list[Chunk], list[str]]:
    """Every chunk this index's sources imply, with a description of each source."""
    chunks: list[Chunk] = []
    sources: list[str] = []
    chunker = STRATEGIES[shape.strategy]

    for act_id in shape.acts:
        path = RAW_DIR / f"act-print-{act_id}.html"
        if not path.exists():
            continue
        act = parse_act(
            path.read_text(encoding="utf-8", errors="replace"),
            act_id=act_id,
            source_url=act_print_url(act_id),
        )
        act_chunks = chunker(act)
        chunks.extend(act_chunks)
        sources.append(f"act-{act_id} {act.title} — {len(act_chunks)} chunks")

    if shape.with_schedule and schedule_path().exists():
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
    parser.add_argument(
        "--force",
        action="store_true",
        help="apply even when the change is large enough to be a rebuild",
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
    try:
        shape = shape_of(index)
    except ValueError as exc:
        print(f"cannot update {args.index!r}: {exc}")
        return 2
    chunks, sources = desired_chunks(shape)

    print(f"index {args.index}: {before} chunks — {shape.describe()}")
    for source in sources:
        print(f"  source: {source}")

    have = {c.chunk_id: c.content_hash for c in index.chunks}
    want = {c.chunk_id: c.content_hash for c in chunks}
    added = len(want.keys() - have.keys())
    removed = len(have.keys() - want.keys())
    changed = sum(1 for k in want.keys() & have.keys() if want[k] != have[k])

    churn = (added + removed) / before if before else 1.0
    if churn > REBUILD_THRESHOLD and not args.force:
        print()
        print(
            f"refusing: this would add {added} and remove {removed} of {before} "
            f"chunks ({churn:.0%} of the index)."
        )
        print(
            "That is a rebuild, not an update, and an index that quietly changes "
            "shape stops being comparable with the runs already recorded against it."
        )
        print(
            f"  to rebuild deliberately: python -m app.retrieval.build "
            f"--strategy {shape.strategy}"
            + (" --with-schedule" if shape.with_schedule else "")
        )
        print("  to proceed anyway:       add --force")
        return 2

    if args.dry_run:
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
