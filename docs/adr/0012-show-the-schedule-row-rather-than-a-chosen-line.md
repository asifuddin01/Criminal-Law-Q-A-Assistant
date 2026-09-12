# 12. Show the Schedule II row, rather than a line chosen from it

**Status:** Accepted · **Date:** 2026-09-12
**Relates to:** the structured offence lookup described in
[architecture.md](../architecture.md) and the citation contract in
[ADR 0011](0011-what-counts-as-a-verbatim-quotation.md).

## Context

Schedule II is a table. A row associates an offence with its procedural attributes —
cognizable, bailable, compoundable, the court that tries it, the punishment, whether
process issues as a warrant or a summons — and section 4(1)(b) and 4(1)(f) of the Code
define "bailable offence" and "cognizable offence" by reference to it. Questions of that
shape are answered there and nowhere else in the corpus.

Rows are indexed as prose, so that "is theft bailable" embeds near them rather than near
a run of column headers. The model therefore sees six sentences and quotes one of them.
Which one is a choice, and it is a choice a small model gets wrong. Asked whether theft
is a bailable offence, the local model answered correctly and quoted this:

> This is a cognizable offence: the police may arrest without a warrant.

The quotation is verbatim. It verified. It is about a different column. The reader was
left with a one-sentence conclusion and an excerpt supporting something nobody asked,
and the deployed demo showed exactly that.

Two responses were available. Prompt the model to quote the line that carries the point
— which was already in the prompt, and which a 3B model will go on getting wrong — or
stop asking a model for something the parse already holds exactly.

The columns are parsed at ingestion. Nothing about the row needs to be selected,
summarised or generated: it is data, and it was being withheld from the reader because
the only path to it ran through the model's choice of sentence.

## Decision

A citation to Schedule II carries its row. `VerifiedCitation` gains an `OffenceFacts`
record populated from the parsed entry, the API returns it as `citation.offence`, and
both interfaces render it in full beneath the heading, above the excerpt, labelled as
coming from the parsed table rather than from the model.

Citations to a section of an act carry no such record and render none. A section is
prose; there are no columns to show, and the excerpt is the right unit for it.

`depends` stays `depends`. Many rows read "according as the offence abetted is bailable
or not", and the schedule genuinely declines to answer for them. Rendering that as "No"
would convert an honest abstention into a wrong answer — the same reasoning that put
`Triable.DEPENDS` in the parser rather than a boolean.

The excerpt is still shown, still checked, and still counted the same way. This adds a
second, deterministic path to the same source; it removes nothing.

## Consequences

The answer to an offence-classification question no longer depends on a small model
choosing the right sentence out of a table. What the table says is on the page whichever
line was quoted, and whichever model answered.

Nothing here is generated, so nothing here can be fabricated — the failure mode the
validation gate exists to catch does not apply to a field copied out of the parse. It is
also the first thing in an answer that the model cannot influence at all, which is worth
stating plainly: the more of an answer that comes from the parse, the less of it rests on
the gate.

The metrics are untouched. Excerpt validity, misattribution and fabrication are all
properties of what the model wrote, and this changes what is displayed beside it, not
what is measured. A run scored before this decision and a run scored after are
comparable.

The cost is duplication when a row's excerpt repeats what the columns already say: a
card can now read "Bailable: No" above the quotation "This offence is not bailable."
That is accepted. The excerpt is evidence for the answer and the row is the source it
came from, and seeing both is how a reader checks one against the other.
