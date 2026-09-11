"""Vector index.

Exact search over an in-memory matrix rather than an approximate index in a separate
service. The corpus is a few hundred acts' worth of chunks at most — hundreds, not
millions — and at that size exact cosine search costs under a millisecond while
returning true nearest neighbours.

An approximate index would add a service to run, a recall parameter to tune, and a
second source of retrieval error to disentangle from the chunking strategy this
project is actually measuring. See ADR 0009.
"""

from __future__ import annotations

import json
import pathlib
import time
from dataclasses import asdict, dataclass

import numpy as np

from app.retrieval.chunking import Chunk
from app.retrieval.embeddings import DEFAULT_MODEL, embed, embed_one

INDEX_DIR = pathlib.Path(__file__).resolve().parents[3] / "data" / "index"


@dataclass(frozen=True, slots=True)
class Hit:
    chunk: Chunk
    score: float


@dataclass(frozen=True, slots=True)
class IndexUpdate:
    """What an incremental update did.

    Reported rather than inferred, because the value of an incremental update is
    entirely in what it *skipped*, and a claim to have skipped work is worth nothing
    without the count.
    """

    added: int
    changed: int
    unchanged: int
    removed: int
    seconds: float

    @property
    def embedded(self) -> int:
        return self.added + self.changed

    @property
    def total(self) -> int:
        return self.added + self.changed + self.unchanged

    def summary(self) -> str:
        if not self.total and not self.removed:
            return "index unchanged"
        # Never round to 100% while anything was embedded: a summary claiming
        # nothing was re-embedded, next to a count saying one chunk was, is the kind
        # of small dishonesty that makes a reader distrust the rest of the numbers.
        proportion = self.unchanged / self.total if self.total else 0.0
        saved = (
            f"{proportion:.1%}"
            if self.embedded and proportion > 0.995
            else f"{proportion:.0%}"
        )
        return (
            f"{self.added} added, {self.changed} changed, "
            f"{self.unchanged} unchanged, {self.removed} removed — "
            f"embedded {self.embedded} of {self.total} chunks "
            f"({saved} reused) in {self.seconds:.1f}s"
        )


class VectorIndex:
    def __init__(
        self, chunks: list[Chunk], vectors: np.ndarray, model_name: str
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunk and vector counts differ")
        self.chunks = chunks
        self.vectors = vectors
        self.model_name = model_name

    def __len__(self) -> int:
        return len(self.chunks)

    @classmethod
    def build(
        cls, chunks: list[Chunk], *, model_name: str = DEFAULT_MODEL
    ) -> VectorIndex:
        vectors = embed([c.text for c in chunks], model_name=model_name)
        return cls(chunks, vectors, model_name)

    def search(self, query: str, *, k: int = 10) -> list[Hit]:
        if not self.chunks:
            return []
        # Vectors are pre-normalised, so the dot product is cosine similarity.
        scores = self.vectors @ embed_one(query, model_name=self.model_name)
        top = np.argsort(-scores)[:k]
        return [Hit(chunk=self.chunks[i], score=float(scores[i])) for i in top]

    def update(self, chunks: list[Chunk]) -> IndexUpdate:
        """Bring the index in line with `chunks`, embedding only what changed.

        Chunks are matched on `chunk_id` and compared on `content_hash`. A chunk
        whose text is unchanged keeps the vector it already has, so adding an act to
        a corpus costs the new act's embeddings and nothing else, and correcting one
        section re-embeds one section.

        Vectors are reused by copying existing rows rather than re-running the model
        on them — the whole point is not to run the model on them.
        """
        started = time.perf_counter()
        existing = {
            chunk.chunk_id: (index, chunk.content_hash)
            for index, chunk in enumerate(self.chunks)
        }

        keep_rows: list[int] = []
        keep_chunks: list[Chunk] = []
        to_embed: list[Chunk] = []
        added = changed = unchanged = 0

        for chunk in chunks:
            previous = existing.pop(chunk.chunk_id, None)
            if previous is None:
                added += 1
                to_embed.append(chunk)
            elif previous[1] != chunk.content_hash:
                changed += 1
                to_embed.append(chunk)
            else:
                unchanged += 1
                keep_rows.append(previous[0])
                keep_chunks.append(chunk)

        removed = len(existing)

        fresh = (
            embed([c.text for c in to_embed], model_name=self.model_name)
            if to_embed
            else np.zeros((0, self.vectors.shape[1]), dtype=np.float32)
        )
        reused = (
            self.vectors[keep_rows]
            if keep_rows
            else np.zeros((0, self.vectors.shape[1]), dtype=np.float32)
        )

        self.chunks = keep_chunks + to_embed
        self.vectors = np.vstack([reused, fresh]) if len(self.chunks) else reused

        return IndexUpdate(
            added=added,
            changed=changed,
            unchanged=unchanged,
            removed=removed,
            seconds=time.perf_counter() - started,
        )

    def save(self, name: str) -> pathlib.Path:
        destination = INDEX_DIR / name
        destination.mkdir(parents=True, exist_ok=True)
        np.save(destination / "vectors.npy", self.vectors)
        with (destination / "chunks.jsonl").open("w", encoding="utf-8") as handle:
            for chunk in self.chunks:
                handle.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
        (destination / "meta.json").write_text(
            json.dumps({"model_name": self.model_name, "count": len(self.chunks)}),
            encoding="utf-8",
        )
        return destination

    @classmethod
    def load(cls, name: str) -> VectorIndex:
        source = INDEX_DIR / name
        meta = json.loads((source / "meta.json").read_text(encoding="utf-8"))
        chunks = [
            Chunk(**json.loads(line))
            for line in (source / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        vectors = np.load(source / "vectors.npy")
        return cls(chunks, vectors, meta["model_name"])

    @classmethod
    def exists(cls, name: str) -> bool:
        return (INDEX_DIR / name / "meta.json").exists()
