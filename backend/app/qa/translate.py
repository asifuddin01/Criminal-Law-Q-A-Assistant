"""Translation of answer prose.

Only the assistant's own explanation is translated. Statutory excerpts, section
numbers and citations are never touched.

That restriction is not stylistic. A quoted excerpt is shown with a badge asserting
it was found verbatim in the stored source text, and a reader can follow the link and
check it. Translate the quotation and the badge asserts something that is no longer
true: the text on screen appears in no statute, and the one claim this system makes
about itself — that its citations can be checked — stops holding.

The official text of the Code as published is English. A Bangla rendering of the
explanation helps a reader; a Bangla rendering of the provision would be this
system's own translation presented as law.
"""

from __future__ import annotations

from app.config import get_settings
from app.llm import ChatMessage, LLMProvider

LANGUAGE_NAMES = {"bn": "Bengali (Bangla)", "en": "English"}

# Bengali legal vocabulary used in Bangladeshi practice. Without these the model
# transliterates — "cognizable" came back as কগনাইজেবল rather than আমলযোগ্য, which
# is the term a Bangladeshi reader would actually encounter in a courtroom or an FIR.
GLOSSARY_BN = """
cognizable offence = আমলযোগ্য অপরাধ
non-cognizable offence = অ-আমলযোগ্য অপরাধ
bailable offence = জামিনযোগ্য অপরাধ
non-bailable offence = অ-জামিনযোগ্য অপরাধ
bail = জামিন
section = ধারা
arrest = গ্রেপ্তার
warrant = পরোয়ানা
investigation = তদন্ত
inquiry = অনুসন্ধান
trial = বিচার
Magistrate = ম্যাজিস্ট্রেট
Court of Session = দায়রা আদালত
High Court Division = হাইকোর্ট বিভাগ
police-officer = পুলিশ কর্মকর্তা
complaint = নালিশ
charge = অভিযোগ গঠন
accused = অভিযুক্ত
confession = স্বীকারোক্তি
summons = সমন
custody = হেফাজত
"""

SYSTEM_PROMPT = """You translate explanations of Bangladeshi criminal procedure.

Translate the text into {language}. Rules:

- Keep section numbers exactly as written, in Latin digits: "section 54" stays "54", \
"561A" stays "561A". Do not convert them to Bengali numerals and do not renumber them.
- Use the established legal vocabulary below rather than transliterating English \
terms. A reader should meet the words used in Bangladeshi courts, not English words \
spelled in Bengali script.
- Keep the names of Acts recognisable.
- Translate only. Do not add, remove, explain or correct anything.
- Return the translation alone, with no preamble and no quotation marks around it.
{glossary}"""

# Shown with every translation. A machine translation of legal information is a
# reading aid, not a source.
NOTICE = {
    "bn": (
        "এই অনুবাদটি স্বয়ংক্রিয়ভাবে তৈরি। আইনের মূল পাঠ ইংরেজিতে প্রকাশিত, এবং "
        "উদ্ধৃত ধারাগুলি ইংরেজিতেই যাচাই করা হয়েছে।"
    ),
    "en": (
        "This translation is machine-generated. The statute is published in English, "
        "and the quoted provisions are verified against that English text."
    ),
}


class UnsupportedLanguage(ValueError):
    pass


async def translate(text: str, *, target: str, provider: LLMProvider) -> str:
    """Translate explanatory prose into the target language."""
    if target not in LANGUAGE_NAMES:
        raise UnsupportedLanguage(
            f"unsupported target {target!r}; expected one of {sorted(LANGUAGE_NAMES)}"
        )
    if not text.strip():
        return ""

    completion = await provider.complete(
        [
            ChatMessage(
                role="system",
                content=SYSTEM_PROMPT.format(
                    language=LANGUAGE_NAMES[target],
                    glossary=GLOSSARY_BN if target == "bn" else "",
                ),
            ),
            ChatMessage(role="user", content=text),
        ],
        max_tokens=get_settings().answer_max_tokens,
    )
    return completion.text.strip()
