"""Incremental index update.

The value of an incremental update is entirely in what it skips, so these tests
count what was embedded rather than only checking the result is correct. A rebuild
that embeds everything also produces a correct index.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.retrieval import chunking
from app.retrieval import index as index_module
from app.retrieval.chunking import CRPC, Chunk
from app.retrieval.index import VectorIndex

DIM = 8


@pytest.fixture
def counting_embed(monkeypatch):
    """Replace the model with a deterministic stand-in that counts what it is asked
    to embed."""
    calls: list[str] = []

    def fake_embed(texts, *, model_name=chunking.CRPC):
        calls.extend(texts)
        if not texts:
            return np.zeros((0, DIM), dtype=np.float32)
        rows = []
        for text in texts:
            vector = np.zeros(DIM, dtype=np.float32)
            for i, ch in enumerate(text[:DIM]):
                vector[i] = (ord(ch) % 17) / 17.0
            norm = np.linalg.norm(vector) or 1.0
            rows.append(vector / norm)
        return np.vstack(rows)

    monkeypatch.setattr(index_module, "embed", fake_embed)
    return calls


def chunk(chunk_id: str, text: str, *, section: str = "1") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        section_number=section,
        marginal_note="",
        part=None,
        chapter=None,
        strategy="test",
        document=CRPC,
    )


def test_unchanged_chunks_are_not_re_embedded(counting_embed):
    original = [chunk("a", "alpha text"), chunk("b", "beta text")]
    index = VectorIndex.build(original)
    counting_embed.clear()

    result = index.update([chunk("a", "alpha text"), chunk("b", "beta text")])

    assert counting_embed == []
    assert (result.added, result.changed, result.unchanged) == (0, 0, 2)
    assert result.embedded == 0


def test_only_the_changed_chunk_is_re_embedded(counting_embed):
    index = VectorIndex.build([chunk("a", "alpha text"), chunk("b", "beta text")])
    counting_embed.clear()

    result = index.update([chunk("a", "alpha text"), chunk("b", "beta text REVISED")])

    assert counting_embed == ["beta text REVISED"]
    assert (result.added, result.changed, result.unchanged) == (0, 1, 1)


def test_adding_a_document_embeds_only_the_new_document(counting_embed):
    """The demonstration this exists for: gaining an act costs that act's
    embeddings and nothing else."""
    index = VectorIndex.build([chunk("a", "alpha"), chunk("b", "beta")])
    counting_embed.clear()

    result = index.update(
        [chunk("a", "alpha"), chunk("b", "beta"), chunk("c", "gamma")]
    )

    assert counting_embed == ["gamma"]
    assert result.added == 1
    assert len(index) == 3


def test_removed_chunks_are_dropped_from_the_index(counting_embed):
    index = VectorIndex.build([chunk("a", "alpha"), chunk("b", "beta")])
    counting_embed.clear()

    result = index.update([chunk("a", "alpha")])

    assert result.removed == 1
    assert len(index) == 1
    assert [c.chunk_id for c in index.chunks] == ["a"]


def test_vectors_stay_aligned_with_their_chunks_after_an_update(counting_embed):
    """The failure this guards against is silent: misaligned rows make retrieval
    return the wrong chunk for a hit, with nothing raising."""
    index = VectorIndex.build([chunk(c, f"text {c}") for c in "abcd"])
    counting_embed.clear()

    index.update(
        [chunk("a", "text a"), chunk("c", "text c CHANGED"), chunk("e", "text e")]
    )

    assert len(index.chunks) == len(index.vectors)
    for position, chunk_object in enumerate(index.chunks):
        expected = index_module.embed([chunk_object.text])[0]
        assert np.allclose(index.vectors[position], expected, atol=1e-6)


def test_an_updated_index_survives_a_save_and_load(counting_embed, monkeypatch):
    monkeypatch.setattr(index_module, "INDEX_DIR", index_module.INDEX_DIR)
    index = VectorIndex.build([chunk("a", "alpha")])
    index.update([chunk("a", "alpha"), chunk("b", "beta")])

    saved = index.save("test_incremental")
    reloaded = VectorIndex.load("test_incremental")

    assert len(reloaded) == 2
    assert {c.chunk_id for c in reloaded.chunks} == {"a", "b"}
    import shutil

    shutil.rmtree(saved, ignore_errors=True)


def test_summary_reports_the_proportion_reused(counting_embed):
    index = VectorIndex.build([chunk(c, f"text {c}") for c in "abcd"])
    counting_embed.clear()

    result = index.update([chunk(c, f"text {c}") for c in "abcd"] + [chunk("e", "new")])

    assert "embedded 1 of 5" in result.summary()
    assert "80% reused" in result.summary()
