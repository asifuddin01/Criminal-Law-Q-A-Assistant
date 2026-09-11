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

    assert len(counting_embed) == 1
    assert "beta text REVISED" in counting_embed[0]
    assert (result.added, result.changed, result.unchanged) == (0, 1, 1)


def test_adding_a_document_embeds_only_the_new_document(counting_embed):
    """The demonstration this exists for: gaining an act costs that act's
    embeddings and nothing else."""
    index = VectorIndex.build([chunk("a", "alpha"), chunk("b", "beta")])
    counting_embed.clear()

    result = index.update(
        [chunk("a", "alpha"), chunk("b", "beta"), chunk("c", "gamma")]
    )

    assert len(counting_embed) == 1
    assert "gamma" in counting_embed[0]
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
        expected = index_module.embed([chunk_object.embedding_text])[0]
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


# --- an update must read what the index is, not assume ------------------------


def _index(chunks) -> VectorIndex:
    return VectorIndex(chunks, np.zeros((len(chunks), DIM), dtype=np.float32), "m")


def _chunk(chunk_id, *, strategy, document=CRPC, section="1", text="text") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        section_number=section,
        marginal_note="",
        part=None,
        chapter=None,
        strategy=strategy,
        document=document,
    )


def test_the_shape_of_an_index_is_read_from_its_own_chunks():
    """Regression, and a bad one.

    `desired_chunks` derived the legal-aware chunk set for whatever index it was
    pointed at. Updating the naive-chunk index therefore replaced its 465 naive
    chunks with 621 legal-aware ones plus the schedule and the Penal Code — making
    the stage 2 and stage 3 indexes copies of the stage 4 corpus. The chunking
    comparison those two stages exist to measure would have gone on reporting
    numbers, from a corpus that no longer differed.
    """
    from app.retrieval.update import shape_of

    naive = _index([_chunk("naive-CrPC-00000", strategy="naive_fixed_size")])
    shape = shape_of(naive)

    assert shape.strategy == "naive_fixed_size"
    assert shape.with_schedule is False


def test_an_index_holding_schedule_rows_is_recognised_as_holding_them():
    from app.retrieval.chunking import SCHEDULE_II
    from app.retrieval.update import shape_of

    mixed = _index(
        [
            _chunk("legal-CrPC-54-0", strategy="legal_aware"),
            _chunk("sch2-379-1", strategy="schedule_rows", document=SCHEDULE_II),
        ]
    )
    shape = shape_of(mixed)

    assert shape.strategy == "legal_aware"
    assert shape.with_schedule is True


def test_an_index_mixing_section_strategies_refuses_rather_than_guessing():
    from app.retrieval.update import shape_of

    mixed = _index(
        [
            _chunk("a", strategy="legal_aware"),
            _chunk("b", strategy="naive_fixed_size"),
        ]
    )

    with pytest.raises(ValueError, match="mixes chunking strategies"):
        shape_of(mixed)


def test_an_update_that_would_replace_the_index_refuses(monkeypatch, capsys):
    """A rebuild wearing an update's clothes is the failure mode worth catching.

    The shape fix stops this particular cause. The guard is there for the next one:
    whatever the reason, an operation that adds and removes most of an index has
    been pointed at the wrong definition, and the runs already recorded against
    that index stop being comparable the moment it silently changes underneath them.
    """
    from app.retrieval import update as update_module

    existing = _index(
        [_chunk(f"legal-CrPC-{n}-0", strategy="legal_aware") for n in range(100)]
    )
    replacement = [
        _chunk(f"naive-CrPC-{n:05d}", strategy="naive_fixed_size") for n in range(100)
    ]

    monkeypatch.setattr(update_module.VectorIndex, "exists", classmethod(lambda c, n: True))
    monkeypatch.setattr(update_module.VectorIndex, "load", classmethod(lambda c, n: existing))
    monkeypatch.setattr(
        update_module, "desired_chunks", lambda shape: (replacement, ["stand-in"])
    )

    code = update_module.main(["--index", "legal_aware"])
    out = capsys.readouterr().out

    assert code == 2
    assert "refusing" in out
    assert "--force" in out
    # Nothing was embedded and nothing was saved.
    assert len(existing) == 100
    assert all(c.strategy == "legal_aware" for c in existing.chunks)
