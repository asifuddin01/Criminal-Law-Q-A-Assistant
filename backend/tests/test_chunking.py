"""Chunking tests.

The naive strategy's defects are asserted rather than avoided. It exists to be the
thing stage 3 is measured against, so a change that quietly improved it would
destroy the comparison.
"""

from __future__ import annotations

import pytest

from app.ingest import cache_path, parse_act
from app.retrieval.chunking import legal_aware, naive_fixed_size

CORPUS = cache_path(75)
corpus_only = pytest.mark.skipif(
    not CORPUS.exists(), reason="corpus not fetched; run: python -m app.ingest"
)


@pytest.fixture(scope="module")
def act():
    if not CORPUS.exists():
        return None
    return parse_act(
        CORPUS.read_text(encoding="utf-8", errors="replace"),
        act_id=75,
        source_url="https://bdlaws.minlaw.gov.bd/act-print-75.html",
    )


@corpus_only
def test_naive_chunks_frequently_cross_section_boundaries(act):
    """The defect the naive strategy exists to demonstrate. If this ever drops to
    zero the strategy has stopped being naive and stage 3's comparison is void."""
    chunks = naive_fixed_size(act)
    crossing = sum(c.crosses_section_boundary for c in chunks)

    assert crossing / len(chunks) > 0.5


@corpus_only
def test_legal_aware_chunks_never_cross_section_boundaries(act):
    chunks = legal_aware(act)

    assert all(not c.crosses_section_boundary for c in chunks)


@corpus_only
def test_every_chunk_carries_a_citable_section(act):
    for strategy in (naive_fixed_size, legal_aware):
        for chunk in strategy(act):
            assert chunk.section_number
            assert act.section(chunk.section_number) is not None


@corpus_only
def test_legal_aware_carries_section_identity_on_every_split(act):
    """A chunk split off the middle of a long section must still say which section
    it belongs to, or it cannot be cited from.

    The identity lives in the chunk's heading, not inside its text. Text is the
    source's own words, so that a quotation can be verified against the statute — a
    heading inside the text gets quoted and then fails verification, because it
    appears in no statute.
    """
    chunks = [c for c in legal_aware(act) if c.section_number == "54"]

    assert len(chunks) > 1, "section 54 is long enough to split"
    for chunk in chunks:
        assert chunk.heading.startswith("Code of Criminal Procedure section 54")
        assert chunk.heading in chunk.embedding_text
        assert "Code of Criminal Procedure section 54" not in chunk.text


@corpus_only
def test_legal_aware_splits_are_trimmed(act):
    for chunk in legal_aware(act):
        assert chunk.text == chunk.text.strip()


@corpus_only
def test_naive_chunks_can_be_attributed_to_a_section_they_barely_contain(act):
    """Concrete instance of the failure: a chunk labelled 54A whose text is
    largely section 55. Retrieval returns the right words under the wrong number."""
    chunks = naive_fixed_size(act)
    mislabelled = [
        c
        for c in chunks
        if c.crosses_section_boundary and c.section_number not in c.text
    ]

    assert mislabelled, "expected boundary-crossing chunks that omit their own number"
