# 1. Record architecture decisions

**Status:** Accepted · **Date:** 2026-09-10

## Context

The assessment brief asks that design choices be documented as they are made, together with
the reasoning for revisiting or changing course, grounded in what the data shows rather than
assumption. A decision recorded after the fact tends to be a justification rather than a
record; it loses the alternatives that were live at the time and the evidence that settled
the question.

## Decision

Architecture decisions are recorded here as numbered, dated, immutable records. An ADR is
never edited to reflect a change of mind. When a decision is revisited, a new ADR supersedes
the old one and states what evidence prompted the change.

Each record states its context, the decision, and its consequences — including the negative
ones. Where a decision is driven by a measurement, it links to the relevant entry in
[EXPERIMENTS.md](../../EXPERIMENTS.md).

## Consequences

Decisions become traceable: any structural choice in the codebase can be followed back to
the constraint or measurement that produced it. Superseded ADRs remain in the history, so
the record shows what was tried and abandoned, not only what survived.

The cost is discipline — a decision taken in code but not recorded here leaves the log
misleading, which is worse than no log.
