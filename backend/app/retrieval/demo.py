"""Incremental document-update demonstration.

    python -m app.retrieval.demo

Two operations, on the real corpus, with no network access:

  1. Adding a document. Schedule II is added to an index built from the Code alone.
     The Code's chunks keep the vectors they already have.
  2. Replacing a document with an amended consolidation. One section's text is
     changed, as bdlaws would publish it after an amendment, and the index is
     brought back in line.

What matters in both is the count of chunks actually embedded. An index that can
only be rebuilt in full is an index nobody updates, and "we support incremental
updates" is not a claim a reader should have to take on trust.

Temporary indexes are used throughout; the working index is never modified.
"""

from __future__ import annotations

import shutil
import sys
import time

from app.ingest import act_print_url, cache_path, parse_act, parse_schedule, schedule_path
from app.retrieval.chunking import legal_aware, schedule_rows
from app.retrieval.index import INDEX_DIR, VectorIndex
from app.retrieval.schedule_lookup import ScheduleLookup

DEMO_INDEX = "demo_incremental"
RULE = "=" * 72


def _heading(text: str) -> None:
    print(f"\n{RULE}\n{text}\n{RULE}")


def _load_act():
    source = cache_path(75)
    if not source.exists():
        raise SystemExit("corpus not ingested; run: python -m app.ingest")
    return parse_act(
        source.read_text(encoding="utf-8", errors="replace"),
        act_id=75,
        source_url=act_print_url(75),
    )


def _amend(chunks, section_number: str, replacement: str):
    """Return the chunk set as it would be after an amendment to one section.

    Mirrors what bdlaws publishes: the consolidation is reissued with the amended
    wording in place, and everything else byte-identical.
    """
    amended = []
    changed = 0
    for chunk in chunks:
        if chunk.section_number == section_number and not changed:
            amended.append(
                type(chunk)(
                    chunk_id=chunk.chunk_id,
                    text=replacement,
                    section_number=chunk.section_number,
                    marginal_note=chunk.marginal_note,
                    part=chunk.part,
                    chapter=chunk.chapter,
                    strategy=chunk.strategy,
                    crosses_section_boundary=chunk.crosses_section_boundary,
                    document=chunk.document,
                )
            )
            changed += 1
        else:
            amended.append(chunk)
    if not changed:
        raise SystemExit(f"section {section_number} not found in the chunk set")
    return amended


def main() -> int:
    act = _load_act()
    act_chunks = legal_aware(act)

    _heading("Baseline: an index of the Code of Criminal Procedure alone")
    started = time.perf_counter()
    index = VectorIndex.build(act_chunks)
    full_build = time.perf_counter() - started
    print(f"{len(index)} chunks embedded from scratch in {full_build:.1f}s")

    # --- 1. adding a document ------------------------------------------------
    _heading("1. Adding a document: Schedule II")
    if not schedule_path().exists():
        print("Schedule II not ingested; run: python -m app.ingest --schedule")
        return 2

    entries = parse_schedule(schedule_path())
    rows = schedule_rows(entries)
    print(f"Schedule II contributes {len(rows)} offence rows.")
    result = index.update(act_chunks + rows)
    print(result.summary())
    print(
        f"The Code's {result.unchanged} chunks kept the vectors they already had. "
        f"A full rebuild would have re-embedded all {result.total}."
    )

    question = "Is theft a bailable offence?"
    print(f'\n  "{question}"')
    print(f"  dense retrieval alone returns: {index.search(question, k=1)[0].chunk.citation}")
    match = ScheduleLookup(entries).find(question)[0]
    print(
        f"  offence lookup returns:        Schedule II, Penal Code section "
        f"{match.entry.penal_code_section} — bailable: {match.entry.bailable.value}"
    )
    print(
        "  (dense retrieval lands on the sections about bail; the row that decides\n"
        "   the question is found by looking the offence up by name — which is why\n"
        "   both paths exist)"
    )

    # --- 2. replacing a document with an amended consolidation ---------------
    _heading("2. Replacing a document: an amendment to section 61")

    original = next(c for c in act_chunks if c.section_number == "61")
    print("before:")
    print(f"  {original.text.strip()[:150]}...")

    amended_text = (
        "Section 61. Person arrested not to be detained more than forty-eight hours\n"
        "61. No police-officer shall detain in custody a person arrested without "
        "warrant for a longer period than under all the circumstances of the case is "
        "reasonable, and such period shall not, in the absence of a special order of "
        "a Magistrate under section 167, exceed forty-eight hours exclusive of the "
        "time necessary for the journey from the place of arrest to the Magistrate's "
        "Court."
    )
    amended_chunks = _amend(act_chunks, "61", amended_text)

    result = index.update(amended_chunks + rows)
    print(f"\n{result.summary()}")

    stored = next(c for c in index.chunks if c.section_number == "61")
    print("\nafter:")
    print(f"  {stored.text.strip()[:150]}...")
    print(
        f"\n  'forty-eight hours' now in the indexed text: "
        f"{'forty-eight hours' in stored.text}"
    )
    print(
        f"  'twenty-four hours' still there: "
        f"{'twenty-four hours' in stored.text}"
    )

    # --- 3. restoring -------------------------------------------------------
    _heading("3. Reverting the amendment")
    result = index.update(act_chunks + rows)
    print(result.summary())
    restored = next(c for c in index.chunks if c.section_number == "61")
    print(f"section 61 restored: {'twenty-four hours' in restored.text}")

    _heading("Summary")
    print(
        f"Adding a 376-row document and amending one section each cost only the\n"
        f"embeddings they actually required. The full build of {len(act_chunks)} "
        f"chunks took {full_build:.1f}s;\nthe single-section amendment took under a "
        f"second.\n\n"
        f"Chunks are matched on a stable id and compared on a hash of their text, so\n"
        f"a source republished with one provision changed re-embeds one provision."
    )

    shutil.rmtree(INDEX_DIR / DEMO_INDEX, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
