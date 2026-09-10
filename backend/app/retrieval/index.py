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
from dataclasses import asdict, dataclass

import numpy as np

from app.retrieval.chunking import Chunk
from app.retrieval.embeddings import DEFAULT_MODEL, embed, embed_one

INDEX_DIR = pathlib.Path(__file__).resolve().parents[3] / "data" / "index"


@dataclass(frozen=True, slots=True)
class Hit:
    chunk: Chunk
    score: float


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
