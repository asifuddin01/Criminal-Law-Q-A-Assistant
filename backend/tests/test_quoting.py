"""What counts as the section's own words.

Each test here is a quotation that a careful lawyer would call faithful and an
exact substring test called fabricated, or the reverse — a label dressed up as law
that must not pass however convenient it would be.
"""

from app.qa.quoting import MIN_QUOTE_CHARS, SourceIndex, canonical, check_quote

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


def test_a_space_left_where_a_footnote_marker_stood_is_not_a_mismatch():
    """Regression. Markers sit between a word and its punctuation.

    Stripping "the Evidence Act, 1872 [7], section 24" leaves "1872 , section 24".
    The gap is an artefact of ingestion; a quotation of the law does not have it.
    """
    body = (
        "163.(1) No police-officer shall offer any such inducement as is mentioned "
        "in the Evidence Act, 1872 , section 24."
    )
    quote = (
        "No police-officer shall offer any such inducement as is mentioned in the "
        "Evidence Act, 1872, section 24."
    )
    assert check_quote(quote, body).verified


def test_a_long_quotation_that_drifts_late_keeps_the_part_that_is_verbatim():
    """Regression from the deployed demo, and the reason it looked broken.

    Asked about section 54 the local model returned 3,838 characters — the whole
    section — of which the first 3,328 were the statute word for word. It had
    inserted one comma three thousand characters in, and the entire quotation
    was rejected. The interface reported "0 excerpts verified" for an answer
    that had quoted the law almost perfectly.
    """
    body = (
        "54. Any police-officer may arrest without warrant any person concerned "
        "in a cognizable offence, or against whom a credible information has "
        "been received, or a reasonable suspicion exists."
    )
    drifted = (
        "Any police-officer may arrest without warrant any person concerned in a "
        "cognizable offence, or against whom a credible information has been "
        "received, or a reasonable, suspicion exists."
    )

    checked = check_quote(drifted, body)

    assert checked.verified
    assert checked.repair == "trimmed"
    # What is shown is verbatim; the drift is not displayed as the statute.
    assert checked.quote in " ".join(body.split())
    assert "reasonable, suspicion" not in checked.quote


def test_a_quotation_that_is_mostly_invented_is_not_rescued_by_its_opening():
    """The floor. Right for a clause and invented after is not drift."""
    body = "54. Any police-officer may arrest without warrant any person concerned."
    mostly_invented = (
        "Any police-officer may arrest without warrant and may thereafter detain "
        "that person for as long as the investigating officer considers it "
        "convenient, without informing a Magistrate of the arrest at all."
    )

    assert not check_quote(mostly_invented, body).verified


def test_the_trimmed_prefix_must_still_clear_the_length_floor():
    body = "54. Any police-officer may arrest without warrant any person concerned."
    assert not check_quote("Any police-officer may " + "x" * 400, body).verified


# Shaped like section 154, where the hosted model's first unverifiable quotation came
# from: the words exact, the hyphen in "police-station" typed as U+2011.
SECTION_154 = (
    "154. Every information relating to the commission of a cognizable offence if "
    "given orally to an officer in charge of a police-station, shall be reduced to "
    "writing by him or under his direction."
)

# Shaped like section 494: a clause, then two consequences in a fixed order.
WITHDRAWAL = (
    "494. Any Public Prosecutor may, with the consent of the Court, at any time "
    "before the judgment is pronounced, withdraw from the prosecution of any person "
    "either generally or in respect of any one or more of the offences for which he "
    "is tried; and upon such withdrawal,- (a) if it is made before a charge has been "
    "framed, the accused shall be discharged in respect of such offence or offences; "
    "(b) if it is made after a charge has been framed, he shall be acquitted in "
    "respect of such offence or offences."
)


def test_a_non_breaking_hyphen_is_the_hyphen_the_statute_has():
    """U+2011 renders exactly like "-". The corpus contains none, so a quotation
    typed with one could never match however faithful its words."""
    quote = "if given orally to an officer in charge of a police\u2011station"
    checked = check_quote(quote, SECTION_154)
    assert checked.verified
    assert checked.repair == ""


def test_folding_the_hyphen_admits_no_other_words():
    """The fold changes a character, never a word. What follows the hyphen here is
    invented, and it must not reach the reader — at most the verbatim opening does,
    under the trimmed-prefix allowance, and is labelled as such."""
    quote = "if given orally to an officer in charge of a police\u2011outpost"
    checked = check_quote(quote, SECTION_154)
    assert "outpost" not in checked.quote
    assert checked.repair != ""


def test_an_elided_fragment_may_end_on_its_own_full_stop():
    """The statute reads "tried; and"; a quotation stopping there ends with "tried."."""
    quote = (
        "Any Public Prosecutor may, with the consent of the Court, ... withdraw from "
        "the prosecution of any person either generally or in respect of any one or "
        "more of the offences for which he is tried."
    )
    checked = check_quote(quote, WITHDRAWAL)
    assert checked.verified
    assert checked.repair == "elision"


def test_edge_punctuation_does_not_pad_a_fragment_past_the_floor():
    """ "tried." is five words' worth of nothing once its full stop is set aside, and
    it must not pass as an elided piece. The opening may still be shown on its own,
    by the prefix allowance — but not as an elision."""
    quote = "Any Public Prosecutor may, with the consent of the Court, ... tried."
    checked = check_quote(quote, WITHDRAWAL)
    assert "elision" not in checked.repair
    assert "tried" not in checked.quote


def _index():
    return SourceIndex([("CrPC:494", WITHDRAWAL), ("CrPC:154", SECTION_154)])


def test_the_cited_sections_own_words_cut_too_short_are_overelided_not_fabricated():
    """Rejected — "shall" is not evidence of anything — but every word is the
    section's, in its order. Scoring it as invented law was the error."""
    quote = (
        "Any Public Prosecutor may, with the consent of the Court, ... shall ... be "
        "acquitted in respect of such offence or offences"
    )
    assert not check_quote(quote, WITHDRAWAL).verified
    assert _index().explain(quote, WITHDRAWAL) == "overelided"


def test_real_pieces_put_in_an_order_the_statute_does_not_are_recomposed():
    """Both pieces are real. Joined this way they say that a withdrawal after a
    charge leads to discharge, which the section does not say."""
    quote = (
        "(b) if it is made after a charge has been framed ... the accused shall be "
        "discharged in respect of such offence"
    )
    assert not check_quote(quote, WITHDRAWAL).verified
    assert _index().explain(quote, WITHDRAWAL) == "recomposed"


def test_an_elision_with_an_invented_piece_is_still_fabrication():
    quote = (
        "Any Public Prosecutor may, with the consent of the Court, ... withdraw the "
        "charge without the leave of any Court whatsoever"
    )
    assert not check_quote(quote, WITHDRAWAL).verified
    assert _index().explain(quote, WITHDRAWAL) == "fabricated"


def test_an_elided_quotation_of_another_section_is_misattributed():
    quote = (
        "Every information relating to the commission of a cognizable offence ... "
        "shall be reduced to writing by him or under his direction"
    )
    assert _index().explain(quote, WITHDRAWAL) == "misattributed:CrPC:154"


def test_a_whole_quotation_found_nowhere_is_fabricated():
    quote = "The Public Prosecutor may withdraw any prosecution at will"
    assert _index().explain(quote, WITHDRAWAL) == "fabricated"
