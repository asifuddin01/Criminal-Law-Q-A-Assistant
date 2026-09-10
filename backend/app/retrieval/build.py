"""Build a vector index for a chunking strategy.

    python -m app.retrieval.build --strategy naive_fixed_size
"""

from __future__ import annotations

import argparse
import sys
import time

from app.ingest import cache_path, parse_act
from app.retrieval.chunking import STRATEGIES
from app.retrieval.embeddings import DEFAULT_MODEL
from app.retrieval.index import VectorIndex


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a retrieval index.")
    parser.add_argument("--strategy", choices=sorted(STRATEGIES), required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--act", type=int, default=75)
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
    chunks = STRATEGIES[args.strategy](act)
    crossing = sum(c.crosses_section_boundary for c in chunks)
    print(f"{args.strategy}: {len(chunks)} chunks, {crossing} cross a section boundary")

    started = time.perf_counter()
    index = VectorIndex.build(chunks, model_name=args.model)
    path = index.save(args.strategy)
    print(f"embedded in {time.perf_counter() - started:.1f}s -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
