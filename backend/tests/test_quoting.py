"""What counts as the section's own words.

Each test here is a quotation that a careful lawyer would call faithful and an
exact substring test called fabricated, or the reverse — a label dressed up as law
that must not pass however convenient it would be.
"""

from app.qa.quoting import MIN_QUOTE_CHARS, canonical, check_quote

# As bdlaws renders it: the substituted words carry brackets, and words repealed
# out of the provision leave "[* * *]" behind.
SECTION_200 = (
    "200. A Magistrate taking cognizance of an offence on complaint shall at once "
    "examine [upon oath the complainant and such of the witnesses present, if any, "
    "as he may consider necessary,] and the substance of the examination shall be "
    "reduced to writing and shall be signed [by the complainant or witness so "
    "examined] [* * *], and also by the Magistrate."
)
NOTE_200 = "Examination of complainant"


def test_amendment_brackets_are_not_part_of_the_quotation():
    """The brackets record how the section was amended, not what it says."""
    quote = (
        "A Magistrate taking cognizance of an offence on complaint shall at once "
        "examine upon oath the complainant"
    )
    assert check_quote(quote, SECTION_200, marginal_note=NOTE_200).verified


def test_repealed_words_close_up():
    """A quotation reads across [* * *]; it does not reproduce the asterisks."""
    quote = "shall be signed by the complainant or witness so examined , and also by the Magistrate"
    assert check_quote(quote, SECTION_200, marginal_note=NOTE_200).verified


def test_matching_as_written_is_not_reported_as_repaired():
    checked = check_quote(
        "and the substance of the examination shall be reduced to writing",
        SECTION_200,
    )
    assert checked.verified
    assert checked.repair == ""
    assert not checked.repaired


def test_leading_label_is_trimmed_not_shown():
    """A model that copies the label quotes honestly; the user must not see it.

    The quotation verifies, and what is displayed is the statute alone.
    """
    quote = (
        "Section 200. Examination of complainant A Magistrate taking cognizance of "
        "an offence on complaint shall at once examine"
    )
    checked = check_quote(quote, SECTION_200, marginal_note=NOTE_200)
    assert checked.verified
    assert checked.repair == "label"
    assert checked.quote.startswith("A Magistrate taking cognizance")
    assert "Examination of complainant" not in checked.quote


def test_bare_section_number_prefix_is_trimmed():
    quote = "200. A Magistrate taking cognizance of an offence on complaint"
    checked = check_quote(quote, SECTION_200, marginal_note=NOTE_200)
    assert checked.verified


def test_marginal_note_alone_is_not_a_quotation():
    """The note is a label. Quoting it alone presents an editor's words as law."""
    long_note = "Procedure when investigation cannot be completed in twenty-four hours"
    body = "167. (1) Whenever any person is arrested and detained in custody..."
    checked = check_quote(long_note, body, marginal_note=long_note)
    assert not checked.verified
    assert checked.quote == ""


def test_elision_is_read_as_an_elision():
    quote = (
        "A Magistrate taking cognizance of an offence on complaint ... and also by "
        "the Magistrate."
    )
    checked = check_quote(quote, SECTION_200)
    assert checked.verified
    assert checked.repair == "elision"


def test_elided_segments_must_appear_in_order():
    """Reordering the statute's words is not quoting it."""
    quote = (
        "and also by the Magistrate ... A Magistrate taking cognizance of an "
        "offence on complaint shall at once"
    )
    assert not check_quote(quote, SECTION_200).verified


def test_elision_cannot_be_used_to_stitch_fragments():
    """Fragments short enough to match anything are not evidence of anything."""
    quote = "A Magistrate ... the ... complaint ... signed ... Magistrate."
    assert not check_quote(quote, SECTION_200).verified


def test_fabricated_text_is_rejected():
    quote = (
        "The Magistrate shall in every case order the complainant to deposit "
        "security before taking cognizance."
    )
    assert not check_quote(quote, SECTION_200, marginal_note=NOTE_200).verified


def test_short_quotes_are_not_checked():
    assert not check_quote("a Magistrate", SECTION_200).verified
    assert len(canonical("a Magistrate")) < MIN_QUOTE_CHARS


def test_trimming_a_label_cannot_smuggle_in_another_section():
    """The remainder is still checked against the section actually cited.

    A model that labels its quotation "Section 61" while citing section 54 gets no
    help from the trim: what is left has to appear in 54.
    """
    section_54 = "54. (1) Any police-officer may, without an order from a Magistrate, arrest."
    quote = (
        "Section 61. No police-officer shall detain in custody a person arrested "
        "without warrant for a longer period than is reasonable."
    )
    assert not check_quote(quote, section_54, marginal_note="When police may arrest").verified


def test_a_label_the_model_invented_does_not_verify_by_being_trimmed():
    """Trimming removes a prefix; it never supplies the words that must follow."""
    section_54 = "54. (1) Any police-officer may, without an order from a Magistrate, arrest."
    assert not check_quote("Section 54.", section_54).verified
    assert not check_quote("Section 54. and nothing else whatsoever", section_54).verified
