# 10. Embedding model: multilingual MiniLM via ONNX

**Status:** Accepted · **Date:** 2026-09-11

## Context

[ADR 0003](0003-llm-provider-strategy.md) committed to supporting Bangla questions
against English statutory text, which requires an embedding model that places a Bangla
question near English text of the same meaning. It named `multilingual-e5-small`.

That model is not offered by fastembed. The available multilingual options are
`intfloat/multilingual-e5-large` at 2.24 GB and
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` at 0.22 GB.

The development machine has 8 GB of unified memory, already shared with a local Ollama
model and the evaluation harness.

## Decision

`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensions, run
through fastembed's ONNX runtime rather than torch.

ONNX rather than torch is deliberate: the runtime is tens of megabytes against a
multi-gigabyte torch install, and startup is seconds rather than tens of seconds, which
matters when the index is rebuilt for every chunking experiment.

Embedding runs on the calling thread at a batch size of 32. ONNX Runtime has deadlocked
for this author at large batch sizes when driven off the main thread, and the
throughput available at this corpus size does not justify revisiting that.

## Consequences

Bangla questions can be embedded into the same space as English statutory text, which
is what the cross-lingual slice of the evaluation set exists to measure. Whether it does
so *well* is a measurement, not an assumption, and the Bangla slice reports it
separately from the English slices for exactly that reason.

A 384-dimensional multilingual model is smaller than the English-only alternatives at
the same size, and multilingual models generally trade some monolingual quality for
coverage. `BAAI/bge-small-en-v1.5` is 0.067 GB and English-only; comparing the two is a
worthwhile experiment once the retrieval pipeline is stable, and would answer whether
Bangla support costs English accuracy. It is recorded here as a candidate rather than
run now, because changing two variables at once — chunking and embedding — would make
neither measurable.

The model choice is a constructor argument threaded through `VectorIndex.build`, and an
index records the model it was built with, so a mismatched query model is detectable
rather than silently wrong.
