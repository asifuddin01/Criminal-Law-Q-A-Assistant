"""Entry point for a Hugging Face Gradio Space.

Docker Spaces are not available on this account's tier, so the application runs
under the `gradio` SDK. That SDK does not require the app to *be* a Gradio
interface — Spaces runs `python app.py` and proxies port 7860 — so what serves
that port is this project's own FastAPI application: the exported Next.js
frontend at `/`, the API under `/api`.

Running FastAPI under the gradio SDK is not a documented pattern (every
documented FastAPI-on-Spaces example uses Docker, which is the tier we do not
have), so this file hedges rather than assumes. A real, working Gradio interface
onto the same pipeline is mounted at `/gradio/`. If the runtime looks for a
Gradio app it finds one; if the static serving misbehaves, that interface still
answers questions with the same retrieval, the same citations and the same
verification. It is a fallback, not the product.

Everything a Dockerfile would do at build time is committed instead, because
this SDK has no build step: `deploy/push-to-space.sh` exports the frontend and
precomputes the Schedule II parse before pushing.
"""

from __future__ import annotations

import os
import pathlib
import sys

# Named space_app.py, not app.py, on purpose: a module called `app` at the
# repository root shadows the `app` package under backend/, and every
# `import app.something` would then resolve to this file. The entrypoint is
# pointed at by `app_file` in the Space README, so the name is free to be safe.
ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

# Point fastembed at the Hugging Face hub cache, which is where `preload_from_hub`
# in the Space README puts the model at build time. fastembed uses the same
# on-disk layout the hub does (`models--<org>--<name>/snapshots/...`), so the
# preloaded copy is found rather than fetched again — this is how a Space with no
# build step still avoids paying a 240 MB download on the first question.
#
# Left to itself fastembed caches under the system temp directory, which a host
# is free to hand back empty on every start. Set before the retrieval code is
# imported. HF_HOME is deliberately not set: the preload does not follow it.
os.environ.setdefault(
    "EMBEDDING_CACHE_DIR",
    str(pathlib.Path.home() / ".cache" / "huggingface" / "hub"),
)

import gradio as gr  # noqa: E402
import uvicorn  # noqa: E402

try:  # Present on a Space, absent when this file is run locally.
    import spaces  # noqa: E402
except ModuleNotFoundError:
    spaces = None
from starlette.responses import RedirectResponse  # noqa: E402

from app.legal import DISCLAIMER  # noqa: E402
from app.main import app as api  # noqa: E402
from app.qa.validation import validate  # noqa: E402
from app.services import get_corpora, get_qa, get_schedule  # noqa: E402


async def answer_question(question: str) -> str:
    """The same pipeline the API uses, rendered as Markdown.

    Deliberately not a reimplementation: retrieval, generation and the citation
    gate are the ones in app/, so this cannot drift into answering differently
    from the real interface.
    """
    question = (question or "").strip()
    if not question:
        return "Ask a question about the Code of Criminal Procedure."

    try:
        answer = await get_qa().answer(question)
    except Exception as exc:  # noqa: BLE001 — surfaced to the user, not swallowed
        return f"**Unavailable.** {exc}"

    if answer.error:
        return f"**Unavailable.** {answer.error}"

    result = validate(answer, get_corpora(), schedule=get_schedule())
    if result.refused:
        return f"**Withheld.** {result.reason or answer.text}"

    lines = [answer.text, "", "---", ""]
    for citation in result.citations:
        heading = (
            f"Schedule II · Penal Code s.{citation.section}"
            if citation.source == "ScheduleII"
            else f"Section {citation.section}"
        )
        note = f" — {citation.marginal_note}" if citation.marginal_note else ""
        lines.append(f"**{heading}**{note}")
        if citation.quote:
            lines.append(f"> {citation.quote}")
        for amendment in citation.amendments:
            when = amendment.effective_from or "date not stated"
            lines.append(f"*{amendment.operation}, in force from {when}*")
        if citation.source_url:
            lines.append(f"[Read it on bdlaws.minlaw.gov.bd]({citation.source_url})")
        lines.append("")
    return "\n".join(lines)


if spaces is not None:

    @spaces.GPU(duration=1)
    def _zerogpu_probe() -> str:
        """Declared because ZeroGPU will not start a Space without one.

        `No @spaces.GPU function detected during startup` is a hard failure, and
        this account's free tier offers ZeroGPU and nothing else — CPU basic
        needs a subscription. So the decorator has to exist.

        It is never called, and that is not a workaround so much as the honest
        answer: there is no GPU work here. Retrieval embeds one short query with
        an ONNX model where a host-to-device transfer would cost more than the
        arithmetic it saves, and the language model is an HTTP request to
        somebody else's accelerator. The Space runs on the CPU it is given and
        consumes none of the shared GPU pool it is admitted to.
        """
        return "ok"


with gr.Blocks(title="Criminal Law Q&A — Bangladesh") as fallback:
    gr.Markdown(
        "## Criminal Law Q&A — Bangladesh\n"
        "A plain fallback interface. The full one is at the root URL of this Space.\n\n"
        f"> {DISCLAIMER}"
    )
    box = gr.Textbox(label="Question", placeholder="Is theft a bailable offence?")
    out = gr.Markdown(label="Answer")
    gr.Button("Ask", variant="primary").click(answer_question, box, out)
    box.submit(answer_question, box, out)

application = gr.mount_gradio_app(api, fallback, path="/gradio")


# A Mount at "/gradio" answers "/gradio/" and redirects "/gradio" to it — but the
# static export below is mounted at "/" and would swallow that redirect, so the
# slash-less path is handled explicitly.
@application.get("/gradio", include_in_schema=False)
async def _gradio_slash() -> RedirectResponse:
    return RedirectResponse("/gradio/")


# The exported frontend matches every path. Starlette tries routes in order, so
# it has to be considered last; anything mounted after it is unreachable while
# still looking mounted.
_routes = application.router.routes
for _index, _route in enumerate(_routes):
    if getattr(_route, "name", None) == "web":
        _routes.append(_routes.pop(_index))
        break

if __name__ == "__main__":
    uvicorn.run(application, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
