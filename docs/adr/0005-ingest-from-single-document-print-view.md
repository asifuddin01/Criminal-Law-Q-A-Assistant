# 5. Ingest from the single-document print view

**Status:** Accepted · **Date:** 2026-09-10
**Supersedes:** [ADR 0002](0002-reassemble-pages-into-legal-sections.md)

## Context

ADR 0002 committed us to a two-pass crawl of 594 per-section URLs, extracting the section
number from each page's `<title>` and reassembling fragments into whole sections, because
the per-section endpoints split a legal section by marginal note and continuation pages
carry no section number.

That reasoning was sound given the endpoints surveyed. It was also unnecessary, because a
better endpoint exists and had not been surveyed.

`/act-print-75.html` serves the entire Code of Criminal Procedure as one document:
approximately 554,400 characters, section markers running from 1 to 565, PART and CHAPTER
headings inline, marginal notes as inline headers within sections, and 599 numbered
amendment footnotes. See [DATA_SOURCE.md](../../DATA_SOURCE.md) finding 6.

The single-document view preserves the section grouping that the per-section endpoints
destroy. Section 1 appears as a continuous run with its marginal notes as internal headers
and subsection numbering intact. The problem ADR 0002 set out to solve does not exist at
this endpoint.

## Decision

Ingestion fetches `/act-print-<id>.html` — one request per act — and parses the whole
document into sections by locating section markers in document order.

The per-section crawl described in ADR 0002 is retained in the codebase as a documented
fallback for any act whose print view is unavailable or malformed, but it is not the default
path and is not exercised by the primary corpus.

Fetches are cached to disk on first retrieval, keyed by URL and content hash, so that
repeated pipeline runs during development do not repeatedly hit a government server.

## Consequences

One request replaces 594. Ingestion becomes fast enough to re-run freely during development,
which matters because the chunking experiments in stages 2 through 4 each require a full
reindex.

The number-inheritance heuristic is deleted rather than debugged. Heuristics that assign
identity to a document are exactly the kind of code that fails silently and produces
confidently mislabelled citations, so removing the need for one is a correctness gain and
not merely a simplification.

Amendment provenance improves. All 599 footnotes are present in one document with their
markers, so marker-to-footnote resolution is a within-document lookup rather than a
cross-page join.

Parsing gets harder in one respect: a 554k-character document must be segmented correctly,
and a segmentation bug now affects the whole act at once rather than one page. Section
boundary detection is therefore covered by tests that assert the recovered section count and
spot-check known boundaries, including the irregular ones — lettered sections such as 4A and
46B, and repealed sections that carry no body text.

## Why this is recorded rather than quietly applied

ADR 0002 was not wrong about the endpoints it examined; it was wrong about having examined
enough of them. The correction came from being pointed at a URL, not from a measurement.

The general lesson is recorded here deliberately: survey the full surface of a source before
designing around any part of it. A pipeline had already been designed, and would have been
built and tested, to solve a problem that a different endpoint does not have.
