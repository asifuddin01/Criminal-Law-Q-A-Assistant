# 2. Reassemble source pages into legal sections before chunking

**Status:** Superseded by [ADR 0005](0005-ingest-from-single-document-print-view.md) · **Date:** 2026-09-10

## Context

The source site publishes the Code of Criminal Procedure one *marginal note* at a time
rather than one *section* at a time. Section 1 occupies two URLs, section 3 occupies four,
and the table of contents yields 594 links. Continuation pages carry no section number in
their body text — the page for "Extent" gives no indication that it belongs to section 1.
See [DATA_SOURCE.md](../../DATA_SOURCE.md) for the full survey.

The obvious ingestion design — one URL, one document, one chunk — is therefore wrong in a
way that is easy to miss. It produces a corpus that retrieves plausible text and cites it as
"Extent", with no section number a user could verify. For a system whose entire value rests
on citation accuracy, this is a correctness failure rather than a formatting one.

## Decision

Ingestion runs in two passes. The first fetches every page and extracts the section number
from the `<title>` element, which carries it in the form `... | 4. Definitions`. The second
groups pages by section number, ordering by position in the table of contents, and emits one
logical document per legal section with its marginal notes as internal structure.

Continuation pages whose title carries no number inherit the number of the most recent
numbered page in table-of-contents order.

The section is the unit of citation. Chunking operates *within* reassembled sections, never
across them.

## Consequences

Citations can always name a section, because the section is the atom of the corpus.
Subsection and clause boundaries survive into retrieval, so an answer about s.4(1)(b) can
quote that clause rather than a window of characters that happens to overlap it.

Sections vary enormously in length — some are a sentence, section 4 is several pages — so
a single fixed chunk size cannot serve both. Long sections are split at subsection
boundaries with the section header repeated into each chunk, so that every chunk carries the
identity needed to cite it.

The two-pass design costs a second traversal and requires the table of contents to be
fetched first. This is negligible against a corpus of a few hundred pages, and the
ordering it provides is what makes number inheritance safe.

We will not assume this reassembly is correct. Stage 2 of the build deliberately ships the
naive one-URL-one-chunk pipeline first and measures it, so that the improvement from
reassembly is a recorded number rather than an assertion.
