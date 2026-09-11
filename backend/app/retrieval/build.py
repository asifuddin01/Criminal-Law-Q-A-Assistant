"""Build a vector index for a chunking strategy.

    python -m app.retrieval.build --strategy naive_fixed_size
"""

from __future__ import annotations

import argparse
import sys
import time

from app.ingest import (
    DocumentRole,
    cache_path,
    parse_act,
    parse_schedule,
    schedule_path,
)
from app.retrieval.chunking import STRATEGIES, schedule_rows
from app.retrieval.embeddings import DEFAULT_MODEL
from app.retrieval.index import VectorIndex


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a retrieval index.")
    parser.add_argument("--strategy", choices=sorted(STRATEGIES), required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--act", type=int, default=75)
    parser.add_argument(
        "--with-schedule",
        action="store_true",
        help=(
            "include Schedule II rows, so offence-classification questions are "
            "answerable; saves under <strategy>_schedule"
        ),
    )
    args = parser.parse_args(argv)

    source = cache_path(args.act)
    if not source.exists():
        print(f"act {args.act} not fetched; run: python -m app.ingest {args.act}")
        return 2

    act = parse_act(
        source.read_text(encoding="utf-8", errors="replace"),
        act_id=args.act,
        source_url=f"https://bdlaws.minlaw.gov.bd/act-print-{args.act}.html",
    )
    if act.role is not DocumentRole.OPERATIVE:
        # ADR 0006. Refused rather than warned about: an index is built once and
        # queried for weeks, and nothing downstream would show that a provision it
        # answered from was an instruction to amend rather than a provision.
        print(
            f"act {args.act} is {act.role.value}, not operative law: {act.title!r}\n"
            "An amending act's text is a diff, not a provision, and indexing it "
            "would let it answer questions about what the law provides.\n"
            "See docs/adr/0006-document-roles-separate-operative-law-from-"
            "amending-instruments.md"
        )
        return 2

    chunks = STRATEGIES[args.strategy](act)
    crossing = sum(c.crosses_section_boundary for c in chunks)
    print(f"{args.strategy}: {len(chunks)} chunks, {crossing} cross a section boundary")

    name = args.strategy
    if args.with_schedule:
        source = schedule_path()
        if not source.exists():
            print("Schedule II not fetched; run: python -m app.ingest --schedule")
            return 2
        rows = schedule_rows(parse_schedule(source))
        chunks = chunks + rows
        name = f"{args.strategy}_schedule"
        print(f"schedule: {len(rows)} rows added ({len(chunks)} chunks total)")

    started = time.perf_counter()
    index = VectorIndex.build(chunks, model_name=args.model)
    path = index.save(name)
    print(f"embedded in {time.perf_counter() - started:.1f}s -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
