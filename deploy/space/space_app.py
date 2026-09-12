"""Entry point for a Hugging Face Gradio Space.

Docker Spaces are not on this account's tier and CPU-basic hardware needs a
subscription, so this runs under the `gradio` SDK on ZeroGPU — which allocates a
GPU only inside `@spaces.GPU` calls, and this application never makes one.

The interface is the project's own: the Next.js application, exported to static
files and served from the root of this Space by the process that serves the API.
One origin, no Node at runtime, which is why the production build asks for
`/api/ask` with no host in front of it.

Gradio's Blocks are still built and launched, because ZeroGPU will not start a
Space that declares no `@spaces.GPU` function and only `launch()` reports one.
Its interface is the fallback: it is served at the root whenever the export is
absent, and displaced by the real one when it is not.

Everything a build step would prepare is committed instead, because this SDK has
none: the parsed Schedule II, the corpus and the vector index. The embedding
model comes from `preload_from_hub` in the Space README.

Two platform behaviours this file exists to accommodate, both found the hard way:

  - Spaces *imports* this module and launches the Blocks it finds, so a
    `__main__` block never runs there.
  - Gradio 6 renders server-side by default on Spaces, putting a Node proxy on
    the public port that forwards only Gradio's own routes to Python. Anything
    mounted on the Python app is unreachable until that is turned off.
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
# local_model.py sits beside this file at the Space root.
sys.path.insert(0, str(ROOT))

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
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402

from app.api.routes import router as api_router  # noqa: E402
from app.legal import DISCLAIMER  # noqa: E402
from app.qa.validation import validate  # noqa: E402
from app.qa.failures import explain  # noqa: E402
from app.services import (  # noqa: E402
    describe_local_model,
    get_corpora,
    get_qa,
    get_schedule,
    local_provider_reachable,
    warm,
)


if spaces is not None:

    @spaces.GPU(duration=1)
    def _zerogpu_probe() -> str:
        """Declared because ZeroGPU will not start a Space without one.

        `No @spaces.GPU function detected during startup` is a hard failure, and
        this account's free tier offers ZeroGPU and nothing else — CPU basic
        needs a subscription. So the decorator has to exist, and the platform
        only counts it once `Blocks.launch()` fires the report that declares it.

        It is never called, and that is not a workaround so much as the honest
        answer: there is no GPU work here. Retrieval embeds one short query with
        an ONNX model where a host-to-device transfer would cost more than the
        arithmetic it saves, and the language model is an HTTP request to
        somebody else's accelerator. The Space runs on the CPU it is given and
        consumes none of the shared GPU pool it is admitted to.
        """
        return "ok"


# The exported Next.js application, placed here by deploy/push-to-space.sh.
WEB = ROOT / "web"

HOSTED_LABEL = "Hosted — openai/gpt-oss-120b"
LOCAL_LABEL = "Local — qwen2.5:3b-instruct"

# A local model already running — the normal case when this project is run on a
# development machine.
LOCAL_AVAILABLE = local_provider_reachable()

# Otherwise, fetch and start one here. A Space has no persistent storage, so this
# is 1.4 GB of Ollama runtime plus 1.9 GB of weights on every cold start, and
# inference then runs on two shared vCPUs. It is done on a background thread so
# the hosted model answers from the first second, and every failure becomes a
# status string rather than an exception — a Space that will not start is worse
# than one with a single model.
LOCAL = None
if not LOCAL_AVAILABLE and os.environ.get("ENABLE_LOCAL_MODEL", "1") != "0":
    from local_model import LocalModel

    LOCAL = LocalModel()
    LOCAL.start_in_background()

# Both are offered. Choosing the local one before it has arrived reports what it
# is doing rather than failing, which is the difference between "still
# downloading" and "broken".
PROVIDERS = {HOSTED_LABEL: "groq", LOCAL_LABEL: "ollama"}


def local_status() -> str:
    """What the local model is doing, for the interface and for its failures."""
    if LOCAL_AVAILABLE:
        return "ready"
    if LOCAL is None:
        return "disabled"
    return LOCAL.status


def local_usable() -> bool:
    return LOCAL_AVAILABLE or (LOCAL is not None and LOCAL.ready)


def _local_note() -> str:
    """What /api/meta should say while the local model is not answering yet.

    Without this the interface reports "no Ollama server is reachable from this
    deployment" for the first several minutes of every cold start — true, and
    useless to a visitor who cannot start one and is not being told that one is
    on its way.
    """
    status = local_status()
    if status == "disabled":
        return "this deployment runs without a local model"
    return (
        f"{status} — a Space has no persistent storage, so 3.3 GB of runtime and "
        "weights is fetched on every cold start. It answers on two shared vCPUs "
        "once it arrives; the hosted model answers now."
    )


# The API serves the interface here, so it is the API that has to explain this.
describe_local_model(_local_note)


async def answer_question(question: str, provider_label: str | None = None) -> str:
    """Answer through the chosen provider, rendered as Markdown.

    Deliberately not a reimplementation: retrieval, generation and the citation
    gate are the ones in app/, so this interface cannot drift into answering
    differently from the API beside it.
    """
    question = (question or "").strip()
    if not question:
        return "Ask a question about the Code of Criminal Procedure."

    provider = PROVIDERS.get(provider_label or HOSTED_LABEL, "groq")

    if provider == "ollama" and not local_usable():
        return (
            f"**The local model is not ready yet** — {local_status()}.\n\n"
            "It is fetched on every cold start because a Space has no persistent "
            "storage: 1.4 GB of runtime and 1.9 GB of weights. The hosted model "
            "answers now; this one will be selectable when it has arrived."
        )

    try:
        answer = await get_qa(provider).answer(question)
    except Exception as exc:  # noqa: BLE001 — surfaced to the reader, not swallowed
        _, detail = explain(str(exc), local_available=local_usable())
        return f"**Unavailable.** {detail}"

    if answer.error:
        # The same wording the API returns for the same condition. This printed
        # the provider's raw 429 until someone looked at the deployed demo.
        _, detail = explain(answer.error, local_available=local_usable())
        return f"**Unavailable.** {detail}"

    result = validate(answer, get_corpora(), schedule=get_schedule())
    if result.refused:
        return f"**Withheld.** {result.reason or answer.text}"

    lines = [answer.text, "", "---", ""]
    lines.extend(_render_citations(result.citations))
    return "\n".join(lines)


OFFENCE_VALUE = {
    "yes": "Yes",
    "no": "No",
    "depends": "Depends on the underlying offence",
    "unknown": "Not stated in the schedule",
}


def _render_citations(citations) -> list[str]:
    """One block per cited provision, not per quotation.

    A provision can be quoted twice, and rendered once each the list repeats the
    heading and the link and reads as two sources where there is one.

    A Schedule II citation also prints its row. The excerpt beside it is one line
    of a table chosen by the model, and asked whether theft is bailable the local
    model quoted the cognizability line — verbatim, verified, and not the answer.
    The columns come from the parse, so the table can be shown rather than
    selected from.
    """
    grouped: dict[tuple[str, str], list] = {}
    for citation in citations:
        grouped.setdefault((citation.source, citation.section), []).append(citation)

    lines: list[str] = []
    for (source, section), group in grouped.items():
        first = group[0]
        heading = (
            f"Schedule II · Penal Code s.{section}"
            if source == "ScheduleII"
            else f"Section {section}"
        )
        note = f" — {first.marginal_note}" if first.marginal_note else ""
        lines.append(f"**{heading}**{note}")

        if first.offence:
            row = first.offence
            lines.append("")
            lines.append("| The row, from the parsed table | |")
            lines.append("| --- | --- |")
            for label, value in (
                ("Cognizable", OFFENCE_VALUE.get(row.cognizable, row.cognizable)),
                ("Bailable", OFFENCE_VALUE.get(row.bailable, row.bailable)),
                ("Compoundable", OFFENCE_VALUE.get(row.compoundable, row.compoundable)),
                ("Punishment", row.punishment),
                ("Triable by", row.triable_by),
                ("First process", row.warrant_or_summons),
            ):
                if value:
                    lines.append(f"| {label} | {value} |")
            lines.append("")

        for citation in group:
            if citation.quote:
                lines.append(f"> {citation.quote}")
        for amendment in first.amendments:
            when = amendment.effective_from or "date not stated"
            lines.append(f"*{amendment.operation}, in force from {when}*")
        if first.source_url:
            lines.append(f"[Read it on bdlaws.minlaw.gov.bd]({first.source_url})")
        lines.append("")
    return lines


EXAMPLES = [
    "When may a police officer arrest a person without a warrant?",
    "Is theft a bailable offence?",
    "How long can police detain someone before a Magistrate?",
    "পুলিশ কখন বিনা পরোয়ানায় গ্রেপ্তার করতে পারে?",
]


with gr.Blocks(title="Criminal Law Q&A — Bangladesh") as demo:
    gr.Markdown(
        "# Criminal Law Q&A — Bangladesh\n"
        "Answers come only from retrieved statutory text — the Code of Criminal "
        "Procedure, 1898, its Schedule II, and the Penal Code, 1860. Every citation "
        "is checked against the stored source before it is shown, and where the "
        "corpus does not support an answer the system says so instead of "
        "producing one."
    )
    gr.Markdown(f"> {DISCLAIMER}")

    question = gr.Textbox(
        label="Question",
        placeholder="Ask about arrest, bail, investigation, or an offence by name",
        lines=2,
    )

    model = gr.Radio(
        choices=list(PROVIDERS),
        value=HOSTED_LABEL,
        label="Model",
        interactive=True,
        info=(
            "The hosted model shares a free daily allowance. The local one is "
            "free and unmetered, materially weaker, and on a Space it is fetched "
            "on every cold start — 3.3 GB — then runs on two shared vCPUs, so it "
            "is slow. Ask it anything before it has arrived and it will say so."
        ),
    )

    status = gr.Markdown(f"*Local model: {local_status()}*")
    refresh = gr.Button("Check local model", size="sm")
    refresh.click(lambda: f"*Local model: {local_status()}*", None, status)

    ask = gr.Button("Ask", variant="primary")
    gr.Examples(examples=EXAMPLES, inputs=question, label="Try one")
    answer = gr.Markdown(label="Answer")

    ask.click(answer_question, [question, model], answer)
    question.submit(answer_question, [question, model], answer)

    gr.Markdown(
        "This is the fallback interface. The project's own — the Next.js "
        "application in the repository — is served at the root of this Space when "
        "it has been exported into the deployment; you are seeing this one "
        "because it was not. The pipeline is the same either way: the same "
        "retrieval, the same citation validation, the same amendment provenance, "
        "and the API under `/api`.\n\n"
        "Source, evaluation and the experiment log: "
        "https://github.com/asifuddin01/Criminal-Law-Q-A-Assistant"
    )


def _mount_application(server: FastAPI) -> None:
    """Add this project's API to the FastAPI app Gradio has just built.

    The interface is Gradio's. The API is mounted alongside it so the pipeline
    can be exercised directly — `/api/ask` returns the citations, their
    verification status and the amendments behind them as JSON.

    Mounted as a sub-application rather than included with `include_router`:
    modern FastAPI's `include_router` appends a lazy marker resolved when the
    app builds its route table, and by this point that has happened. A mount is
    resolved per request, so it works on an app that is already serving.
    """
    for component, state in warm().items():
        print(f"{component}: {state}", flush=True)

    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    api.include_router(api_router)
    server.mount("/api", api)

    _serve_frontend(server)


def _serve_frontend(server: FastAPI) -> None:
    """Put the project's own interface at the root of the Space.

    The Next.js application is exported to static files at build time, so serving
    it needs no Node process and no second origin — the page and the API come
    from this one server, which is what lets the production build request
    `/api/ask` with no host in front of it.

    Starlette matches routes in the order they appear and Gradio registered `/`
    while it built this app, so these go in front of that rather than after it.
    Everything else Gradio serves — `/config`, `/queue/...`, `/assets/...` — is
    untouched, and the Blocks still launch, which is what ZeroGPU is counting.

    Moving Gradio's page under a prefix instead was tried and rejected. Gradio
    derives the URL its client fetches from the request, and that derivation
    reads `x-forwarded-host` when one is present: behind a Space's proxy the
    prefix is dropped and the page works, run locally it is kept and every asset
    404s. A page that only works deployed is the failure this file has already
    paid for twice.

    With no export present nothing is inserted and Gradio keeps the root, so a
    deployment that ships without one still has an interface.
    """
    index = WEB / "index.html"
    assets = WEB / "_next"
    # Both, because StaticFiles raises on a missing directory and it would raise
    # here — inside the call that builds the server, before anything is serving.
    # An incomplete export should cost the page it shipped, not the Space.
    if not (index.exists() and assets.is_dir()):
        print("web: absent, Gradio's interface serves the root", flush=True)
        return

    async def _index(_request: Request) -> FileResponse:
        return FileResponse(index)

    routes = server.router.routes
    routes.insert(
        0, Mount("/_next", app=StaticFiles(directory=WEB / "_next"), name="next")
    )
    routes.insert(
        0, Route("/", endpoint=_index, methods=["GET", "HEAD"], name="frontend")
    )
    print(f"web: {index}", flush=True)


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
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
    )
