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

## Corpus scope

**Core.** The Code of Criminal Procedure, 1898 (`act-75`) and its amending acts.

**Related legislation**, to be added incrementally and used to demonstrate document
addition without full reindexing:

- The Penal Code, 1860 (Act No. XLV of 1860)
- The Evidence Act, 1872 (Act No. I of 1872)
- The Special Powers Act, 1974
- Nari-o-Shishu Nirjatan Daman Ain, 2000
- The Cyber Security Act, 2023

## Retrieval and provenance policy

Every ingested unit records the source URL, the site page id, the fetch timestamp, and a
content hash. Citations shown to users resolve back to a specific section of a specific act,
and quoted excerpts are verified as substrings of the stored source text before display.

## Terms of use

The corpus is public legislation published by the Government of Bangladesh for public
reference. Ingestion is rate-limited and identifies itself by user agent. Content is used
for reference and citation, and the assistant links back to the official source for every
citation it produces.
