"""Text embedding.

fastembed runs ONNX rather than torch, which matters on an 8 GB machine: the model
is a few hundred megabytes rather than a multi-gigabyte torch install, and startup
is seconds rather than tens of seconds.

Batches are kept modest and embedding runs on the calling thread deliberately.
ONNX Runtime has deadlocked for this author at large batch sizes when driven off the
main thread, and the throughput gain at this corpus size would not be worth the risk.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

# 384-dimensional, ~0.22 GB, covers Bengali alongside English — the requirement from
# ADR 0003 that questions may be asked in Bangla against English statutory text.
# multilingual-e5-small is not offered by fastembed; e5-large is 2.24 GB and too
# heavy for this machine. Alternatives are compared in EXPERIMENTS.md.
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_BATCH = 32


@lru_cache(maxsize=2)
def _model(name: str):
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=name)


def embed(texts: list[str], *, model_name: str = DEFAULT_MODEL) -> np.ndarray:
    """Embed texts into an L2-normalised matrix, one row per text.

    Normalising here means cosine similarity is a dot product downstream, so the
    index does no arithmetic it could get wrong.
    """
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)

    vectors = np.asarray(
        list(_model(model_name).embed(texts, batch_size=EMBEDDING_BATCH)),
        dtype=np.float32,
    )
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def embed_one(text: str, *, model_name: str = DEFAULT_MODEL) -> np.ndarray:
    return embed([text], model_name=model_name)[0]
