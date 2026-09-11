# 6. Documents carry a role; only operative law is retrievable as law

**Status:** Accepted · **Date:** 2026-09-10

## Context

The brief's objective covers the Code of Criminal Procedure "and relevant amendments and
related laws of Bangladesh". The word *amendment* denotes two different things here, and
they require opposite handling.

**Consolidated amendments.** bdlaws publishes the *as-amended* text. What we ingest from
`/act-print-75.html` is already current law. The 599 footnotes are provenance: they say what
changed, under which act, and often from what date.

**Amending instruments.** "The Code of Criminal Procedure (Amendment) Act, 2009 (Act No.
XXXII of 2009)" is itself an act on bdlaws. Its content is not law about criminal procedure
— it is a diff: *"in section 4, for clause (u), the following shall be substituted"*.

Ingesting both into one flat index produces a specific and severe failure. A question about
what section 29B provides retrieves a 1976 ordinance's instruction to omit a word, and the
system presents it as the provision. The text is genuine, the citation resolves, and the
answer is wrong — which is the worst combination available, because nothing looks broken.

For a system whose entire value rests on grounded citation, presenting a diff as operative
law is a correctness failure, not a relevance one.

## Decision

Every ingested document carries a `role`:

| Role | Contents | Retrievable as law |
|---|---|---|
| `operative` | As-amended text of a principal act | Yes |
| `amending` | Amending acts and ordinances | No |
| `schedule` | Schedules and tabular annexes | Yes, via structured lookup |

Default retrieval is restricted to `operative` and `schedule`. Documents with role
`amending` are indexed but reachable only through amendment-provenance queries — questions
*about* how a provision changed — and are never eligible to answer a question about what the
law provides.

Amendment provenance is held as structured records extracted from the footnote apparatus,
not as retrievable prose:

```
{ marker, operation, target_section, target_clause,
  amending_act, act_number, year, effective_from, footnote_text }
```

`operation` is one of `inserted`, `substituted`, `omitted`, `repealed`.

These records attach to the section they modify. They let an answer carry its amendment
history alongside the provision, and they let the system answer questions such as "when was
section 54 last amended?" without the amending act ever entering the answer as law.

## Consequences

The failure mode above is structurally impossible rather than prompt-discouraged. A
retrieval filter is verifiable; an instruction not to quote amending acts is not.

Amendment history becomes a first-class feature rather than a side effect. An answer about a
provision that was substituted in 2009 can say so, with the amending act and its effective
date, because that is a field lookup rather than a retrieval gamble.

The cost is that role assignment must be correct at ingestion. A principal act misfiled as
`amending` becomes invisible; an amending act misfiled as `operative` reintroduces exactly
the bug this decision removes. Role is therefore derived from the act's own title and
structure and asserted in tests, not inferred at query time.

Full point-in-time reconstruction — rendering the text as it stood on an arbitrary past date
— is **not** in scope. We store `effective_from` and can state when a provision changed, but
we do not reconstruct superseded text, because bdlaws publishes only the current
consolidation and the footnotes do not always preserve the replaced wording in full. This is
recorded as a limitation rather than approximated, since a legal assistant that guesses at
historical text is worse than one that declines to provide it.

## Implementation note, 2026-09-12

This decision was recorded before the code existed and was, for some weeks, only recorded.
`parse_act` took a `role` argument defaulting to `OPERATIVE`, nothing derived it, and nothing
downstream checked it. The guarantee held because no amending act had been ingested, which is
not the same thing as holding.

It is now enforced, and at a different point than this ADR describes. The text above proposes
a **retrieval filter** — operative and schedule documents only, applied to the retrieved set.
What is implemented instead excludes a non-operative act from the **index**: `build` refuses
one outright, and the incremental update skips it and names what it skipped.

Index time is the stronger place for it. A retrieval filter leaves the amending text in the
index and relies on every query path applying the filter; excluding it at build time means
there is nothing to filter, and a path that forgets to filter cannot retrieve what was never
embedded. The cost is that changing the rule requires a rebuild rather than a redeploy, which
for a corpus of this size is under a minute.

The role is derived from the act's own title, as the Consequences section requires
(`infer_role`), and asserted in tests. An explicit `role=` still overrides the inference, for
a document that names itself unusually.
