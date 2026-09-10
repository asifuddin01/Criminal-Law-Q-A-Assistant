# Legal Corpus: Source and Structure

## Primary source

[`bdlaws.minlaw.gov.bd`](http://bdlaws.minlaw.gov.bd) — the Legislative and Parliamentary
Affairs Division, Ministry of Law, Justice and Parliamentary Affairs. This is the
authoritative published text of Bangladesh legislation.

The Code of Criminal Procedure, 1898 is **`act-75`**. Table of contents at `/act-75.html`;
individual pages at `/act-75/section-<id>.html`.

## Findings from source survey (2026-09-10)

These were established by direct inspection of the live site before any ingestion code was
written. They are recorded here because two of them materially determine the chunking
strategy, and one determines whether an amendment-aware retrieval layer is feasible at all.

### 1. Pages are server-rendered plain HTML

No JavaScript rendering, no client-side hydration required to reach the statutory text. A
plain HTTP fetch plus an HTML parser is sufficient; a headless browser is not needed.

*Consequence:* ingestion can be a simple, fast, reproducible fetch-and-parse. No browser
automation dependency.

### 2. A site page is **not** a legal section

This is the single most important structural fact about the source.

The site splits one legal section into multiple pages, one per *marginal note*:

| Legal section | Site pages |
|---|---|
| s.1 | `section-14268` (Short title; Commencement), `section-14269` (Extent) |
| s.3 | `section-22875`, `section-24401`, `section-26049`, `section-26050` |

The table of contents yields **594 section links**, which exceeds the number of numbered
sections in the Code. The exact section count will be established by the ingestion pipeline
rather than assumed here.

Critically, **continuation pages carry no section number in their body text**. The page for
`Extent` contains the word "Extent" and the provision text, but nothing identifying it as
part of section 1.

*Consequence:* a pipeline that treats each URL as one retrievable chunk will fragment
sections and emit citations such as *"Extent"* with no section number attached. Pages must
be reassembled into legal sections before chunking.

### 3. The section number is recoverable from the page title

The `<title>` element carries both the number and the marginal note:

```
The Code of Criminal Procedure, 1898 | 4. Definitions
```

*Consequence:* this is the join key for reassembling fragmented pages into whole sections.
Continuation pages whose title lacks a number inherit the number of the most recent
numbered page in table-of-contents order.

### 4. Document hierarchy is present on every page

Each section page carries its full ancestry as text: `PART → CHAPTER → marginal note → body`.

*Consequence:* the hierarchy metadata required for structured citation comes free from the
source and does not need to be reconstructed from the table of contents.

### 5. Amendment provenance is machine-extractable

Amended text is marked inline with a superscript marker and a bracket-delimited span:

```
1[(a) "advocate", used with reference to any proceeding in any Court, means ...]
```

The corresponding footnote at the foot of the page names the operation, the amending act,
and frequently an explicit commencement date:

> 5 Clause (u) was substituted by section 3 of the Code of Criminal Procedure (Amendment)
> Act, 2009 (Act No. XXXII of 2009) (with effect from 1st November, 2007).

Repeals appear inline in the body rather than as footnotes:

```
(d) [Repealed by section 3 and Schedule II of the Repealing and Amending Act, 1923
(Act No. XI of 1923).]
```

*Consequence:* operation type (`inserted` / `substituted` / `omitted` / `repealed`), the
amending act and its number, and in many cases `effective_from` can be extracted by pattern
matching. An amendment-aware layer is therefore grounded in the published record rather
than inferred. This also supplies the incremental-document-update demonstration, since the
amending acts are themselves separate acts on the same site.

### 6. The whole act is available as a single document

*Established 2026-09-10, after findings 1-5 and after ADR 0002 had already been accepted.*

Two further endpoints serve the entire act on one page:

| Endpoint | Size | Contents |
|---|---|---|
| `/act-details-75.html` | ~554,800 chars | Full act plus site navigation chrome |
| `/act-print-75.html` | ~554,400 chars | Full act, print view, minimal chrome |

Both carry the complete Code — section markers run from 1 to 565 — with PART and CHAPTER
headings inline, marginal notes as inline headers, and **599 numbered amendment footnotes**
at the foot of the document.

Crucially, the single-document view **preserves the true section grouping** that the
per-section URLs fragment. Section 1 appears as one continuous run:

```
Short title Commencement
1.(1) This Act may be called the Code of Criminal Procedure, 1898; ...
Extent
(2) It extends to the whole of Bangladesh; ...
```

The marginal note is a header *within* the section rather than a separate document, and
subsection numbering continues naturally.

*Consequence:* the reassembly problem described in finding 2 does not need to be solved. It
was an artefact of choosing the wrong endpoint. Ingesting `/act-print-75.html` requires one
request instead of 594, removes the number-inheritance heuristic and the failure modes that
came with it, and is dramatically more considerate of a government server.

Finding 2 remains recorded because it is still true of the per-section endpoints, and
because any act whose print view is unavailable will have to fall back to that path.

This finding supersedes the ingestion strategy in ADR 0002. See
[ADR 0005](docs/adr/0005-ingest-from-single-document-print-view.md).

### 7. Schedule II is not in the HTML corpus; it is a separate PDF

*Established 2026-09-10.*

The print view contains the act text (to roughly character 455,000) followed by the footnote
apparatus. It does **not** contain the Schedules. The table of contents links the schedule
out to a PDF:

```
https://bdlaws.minlaw.gov.bd/upload/act/2026-05-05-11-47-47-Schedule-II.pdf
```

Verified reachable: `200`, `application/pdf`, 3,840,115 bytes, last modified 2026-05-05.

The two HTML `<table>` elements in the print view are the compoundable-offence tables inside
s.345, not the Schedules.

*Why this matters.* Schedule II is load-bearing for the Code. Section 4(1)(b) defines
*bailable offence* by reference to it, and s.4(1)(f) defines *cognizable offence* by
reference to it. The schedule classifies each Penal Code offence by whether police may
arrest without warrant, whether it is bailable, whether a warrant or summons issues, whether
it is compoundable, and which court may try it.

Questions of the form "is theft bailable?" or "can police arrest without a warrant for
criminal breach of trust?" are therefore answered by the schedule and by nothing else in the
corpus. Without it the system retrieves the *definition* in s.4(1)(b), which is a pointer
rather than an answer, and produces a fluent, correctly cited non-answer.

*Consequence.* Schedule II must be ingested, and it is tabular rather than prose. Prose
chunking would destroy the row structure that carries the meaning — a row associates an
offence with its procedural attributes, and a chunk spanning a row boundary silently
attributes one offence's bailability to another. It is therefore extracted as structured
rows and queried by lookup, with retrieval falling back to it when a question turns on
offence classification.

This also makes the PDF-ingestion capability listed as optional in the brief a requirement
of the core corpus rather than an extra.

## Corpus scope

Membership follows the criterion in [ADR 0007](docs/adr/0007-inclusion-criterion-for-related-laws.md):
an act is in scope if CrPC incorporates it by normative reference, or if it displaces CrPC
procedure. Each document carries a role per
[ADR 0006](docs/adr/0006-document-roles-separate-operative-law-from-amending-instruments.md).

| Document | Role | Source |
|---|---|---|
| Code of Criminal Procedure, 1898 | `operative` | `act-print-75.html` |
| CrPC Schedule II | `schedule` | `upload/act/2026-05-05-11-47-47-Schedule-II.pdf` |
| CrPC amending acts and ordinances | `amending` | Individual acts on bdlaws |
| Penal Code, 1860 | `operative` | bdlaws |
| Evidence Act, 1872 | `operative` | bdlaws |
| Special Powers Act, 1974 | `operative` | bdlaws |
| Nari-o-Shishu Nirjatan Daman Ain, 2000 | `operative` | bdlaws |
| Cyber Security Act, 2023 | `operative` | bdlaws |

Acts beyond CrPC are ingested one at a time, each demonstrating the incremental-update path
and each followed by an evaluation run, so that an addition which degrades retrieval on core
questions is detected rather than presumed harmless.

## Retrieval and provenance policy

Every ingested unit records the source URL, the site page id, the fetch timestamp, and a
content hash. Citations shown to users resolve back to a specific section of a specific act,
and quoted excerpts are verified as substrings of the stored source text before display.

## Terms of use

The corpus is public legislation published by the Government of Bangladesh for public
reference. Ingestion is rate-limited and identifies itself by user agent. Content is used
for reference and citation, and the assistant links back to the official source for every
citation it produces.
