# 9. Exact in-process vector search, not an approximate index service

**Status:** Accepted · **Date:** 2026-09-11
**Amends:** the retrieval row of the technology table in [architecture.md](../architecture.md),
which named Qdrant before the corpus size was known.

## Context

The technology table was written before ingestion existed and named Qdrant on the
reasonable assumption that a vector database is what a retrieval system uses.

The corpus is now measured. The Code of Criminal Procedure yields 465 chunks under the
naive strategy and 621 under the legal-aware one. Adding every related act in
[ADR 0007](0007-inclusion-criterion-for-related-laws.md) puts the corpus in the low
thousands of chunks. At 384 dimensions that is a matrix of a few megabytes.

Approximate nearest-neighbour indexes exist to avoid scanning millions of vectors. At
this scale there is nothing to avoid: an exact scan of a few thousand rows is a single
matrix multiply costing well under a millisecond, against an LLM call of several
seconds.

## Decision

Retrieval is an exact cosine search over an in-memory NumPy matrix, persisted to disk
as a `.npy` alongside chunk metadata as JSONL. No separate service, no Docker
dependency for retrieval.

Vectors are L2-normalised at embedding time, so cosine similarity is a dot product and
the index performs no arithmetic it could get wrong.

## Consequences

Retrieval returns true nearest neighbours. This matters more than the speed: an
approximate index introduces a recall parameter, and recall lost to that parameter is
indistinguishable in the metrics from recall lost to the chunking strategy — which is
the variable stages 2 and 3 exist to measure. Removing that confound is the main
reason for this decision, not performance.

The project keeps one fewer moving part. Anyone cloning the repository can build an
index and run an evaluation without starting a container.

The limit is real and should be stated: this design does not survive a corpus two or
three orders of magnitude larger. If the corpus grows to all Bangladeshi legislation
rather than criminal law, an approximate index becomes necessary and this ADR should be
superseded rather than stretched. The `VectorIndex` interface is deliberately small —
`build`, `search`, `save`, `load` — so that replacement is contained.
