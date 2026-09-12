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
from functools import wraps

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

# Gradio 6 renders server-side by default on Spaces, which puts a Node proxy on
# the public port and forwards only Gradio's own routes to Python behind it. This
# application's routes live on the Python app, so SSR makes every one of them
# unreachable: the deployed Space answered /api/meta with Gradio's page while the
# mounts existed and had already logged their startup, which is a difficult thing
# to diagnose from outside and took the container log to see.
#
# Assignment rather than setdefault: the platform sets this to true, and this has
# to override it. `launch(ssr_mode=None)` reads the variable, and the platform is
# the one calling launch.
os.environ["GRADIO_SSR_MODE"] = "false"

import gradio as gr  # noqa: E402

try:  # Present on a Space, absent when this file is run locally.
    import spaces  # noqa: E402
except ModuleNotFoundError:
    spaces = None
from fastapi import FastAPI  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app.api.routes import router as api_router  # noqa: E402
from app.legal import DISCLAIMER  # noqa: E402
from app.qa.validation import validate  # noqa: E402
from app.services import get_corpora, get_qa, get_schedule, warm  # noqa: E402


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

def _mount_application(server: FastAPI) -> None:
    """Add this application's routes to the FastAPI app Gradio has just built.

    The API is **mounted** as a sub-application rather than included with
    `include_router`. Modern FastAPI's `include_router` appends a lazy marker
    resolved when the app builds its route table; a mount is resolved per
    request and so works whenever it is added.
    """
    for component, state in warm().items():
        print(f"{component}: {state}", flush=True)

    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    api.include_router(api_router)
    server.mount("/api", api)

    static = ROOT / "backend" / "static"
    if (static / "index.html").exists():
        # Gradio serves its own page at "/". The exported frontend is this
        # application's interface, so it takes the root and Gradio's index goes.
        server.router.routes = [
            route
            for route in server.router.routes
            if getattr(route, "path", None) != "/"
        ]
        # Mounted last: it matches every path, so anything added after it would
        # be unreachable — the API mount above included.
        server.mount("/", StaticFiles(directory=static, html=True), name="web")


# Gradio builds its FastAPI app inside `launch()`, and on a Space it is the
# platform that calls `launch()` — this file is imported, not executed, so a
# `__main__` block never runs. That was not a guess in the end: importing the
# module and launching it the way the platform does reproduces exactly what the
# deployed Space served, Gradio's own index page at every path and no API.
#
# Hooking `create_app` is therefore the one point where these routes can reach
# the server that will actually serve them, whoever calls launch.
_original_create_app = gr.routes.App.create_app


@wraps(_original_create_app)
def _create_app(*args, **kwargs):
    server = _original_create_app(*args, **kwargs)
    _mount_application(server)
    return server


gr.routes.App.create_app = staticmethod(_create_app)


if __name__ == "__main__":
    # Local runs only; on a Space the platform launches the Blocks above.
    fallback.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
    )
