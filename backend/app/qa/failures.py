"""What to say when the model cannot be reached.

One definition, used by the API and by the Gradio interface. They had different
ideas of it for exactly as long as it took someone to look at the deployed
demo: the API turned a spent daily allowance into a clear 503, and the interface
printed the provider's raw 429 — `groq: Error code: 429 - {'error': {'message':
'Rate limit reached for model openai/gpt-oss-120b in organization org_01m2...'}}`
— to a reader who has no idea what any of that means or whether the system is
broken.
"""

from __future__ import annotations

from app.llm.rate_limit import is_daily_limit, reset_hint


def explain(message: str, *, local_available: bool = False) -> tuple[int, str]:
    """Turn a provider failure into a status code and something a reader can act on.

    `local_available` says whether a local model is actually running and could
    answer instead. It is passed rather than assumed, because a hosted
    deployment has none — a Hugging Face Space cannot run Ollama — and telling
    someone to switch to a model that is not there is worse than telling them
    to wait.
    """
    message = str(message)

    if is_daily_limit(message):
        hint = reset_hint(message)
        when = f" It frees up in {hint}." if hint else ""
        alternative = (
            " You can switch to the local model below and keep going — it is free "
            "and unmetered, and materially weaker."
            if local_available
            else " There is no local model in this deployment, so the only option "
            "is to wait."
        )
        return 503, (
            "The shared free-tier daily token allowance for the hosted model is "
            f"spent.{when} Nothing is broken: the corpus, retrieval and the "
            "citation checks are all local and still working, and an answer would "
            f"be grounded exactly as the others are.{alternative}"
        )

    lowered = message.lower()
    if any(
        marker in lowered
        for marker in ("connection", "timed out", "timeout", "unreachable")
    ):
        return 503, (
            f"The language model could not be reached: {message}"
            + (
                " The local model is running and can answer instead."
                if local_available
                else ""
            )
        )

    return 502, f"The language model is unavailable: {message}"
