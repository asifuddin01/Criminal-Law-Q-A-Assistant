# Deploying

The application runs as a single container: the frontend is exported to static files and
served by the API process, so the page and the API share an origin. One process, one
port, and no cross-origin configuration to get wrong somewhere nobody can debug it.

## Hugging Face Spaces

**Docker Spaces are gated behind a paid tier on some accounts.** Check the SDK picker at
[huggingface.co/new-space](https://huggingface.co/new-space): if **Docker** shows a
`Paid` badge, use the Gradio route below. The `Dockerfile` in this repository still works
and is still the better deployment where Docker is available — see *Running the container
locally* at the end.

### The Gradio route

The `gradio` SDK does not require the application to *be* a Gradio interface. Spaces runs
the file named by `app_file` and proxies port 7860, and what serves that port here is this
project's own FastAPI application — the exported Next.js frontend at `/`, the API under
`/api`, exactly as the container serves them.

This is not a documented pattern; every documented FastAPI-on-Spaces example uses Docker.
So the entrypoint hedges rather than assumes: a real, working Gradio interface onto the
same pipeline is mounted at `/gradio/`. If the runtime looks for a Gradio app it finds one,
and if static serving misbehaves that interface still answers with the same retrieval, the
same citations and the same verification.

**A Gradio Space has no build step**, so everything the Dockerfile did at build time is
committed by the push script instead: the frontend export, the parsed Schedule II, the
corpus and the index. The embedding model is the exception — it is fetched by
`preload_from_hub` in the Space README. fastembed uses the same on-disk layout as the
Hugging Face hub cache (`models--<org>--<name>/snapshots/…`), so a preloaded copy is found
rather than re-downloaded, which is what keeps a 240 MB fetch off the first question.

### 1. Create the Space

At [huggingface.co/new-space](https://huggingface.co/new-space): **Gradio** SDK, blank
template, public, license blank unless you have chosen one.

**Hardware: whichever free option the account offers.** On some accounts CPU basic is
reserved for PRO subscribers and **ZeroGPU** is the only free choice — that is the case
here, and it is fine. A ZeroGPU Space runs on ordinary CPU and allocates a GPU only inside
`@spaces.GPU` calls. This application never makes one: embeddings are ONNX on CPU and the
language model is an HTTP call. So the GPU is never requested, the 5-minute daily GPU quota
is never touched, and the Space behaves as a CPU Space.

Two ZeroGPU constraints do apply, and both are already handled:

- **Python is restricted to 3.12.12 or 3.10.13.** The Space README pins `3.12.12`, which is
  also valid on CPU basic, so the build is correct on either.
- **Hosting requires an account in good standing** — verified email, older than 30 days. A
  newer account fails in a way that reads like a build error rather than an eligibility one,
  so check that first if the Space will not start.

**ZeroGPU will not start a Space that declares no GPU work.** The startup check fails with
`No @spaces.GPU function detected during startup`, and it is fatal — the build succeeds, the
application starts, and the platform stops it anyway.

There is no honest GPU work in this system to give it. Retrieval embeds one short query with
an ONNX model, where the host-to-device transfer would cost more than the arithmetic it
saves, and the language model is an HTTP request to somebody else's accelerator. So
`space_app.py` declares one `@spaces.GPU` function and never calls it. That is stated plainly
in the code rather than dressed up: the Space runs on the CPU it is given and consumes none
of the shared GPU pool it is admitted to, which is the most considerate thing it can do with
an allocation it did not need.

The import is optional, so the same file still runs locally where the `spaces` package does
not exist.

**Declaring the function is not enough — Gradio has to own the server.** The `spaces`
package reports a Space's GPU functions to the platform from a monkey-patched
`gr.Blocks.launch`: `spaces/zero/__init__.py` registers it with `gradio.one_launch(startup)`.
Nothing else fires that report. A Space that runs its own uvicorn never sends it, and the
platform stops it with the same `No @spaces.GPU function detected during startup` however
many decorated functions the code actually has.

**And the platform, not this file, calls `launch()`.** Spaces *imports* the module named by
`app_file` and launches the Blocks it finds; a `__main__` block never runs. Importing the
module locally and launching it the same way reproduces the deployed behaviour exactly,
which is how this was diagnosed rather than guessed.

**Server-side rendering has to be off for anything mounted on the Python app.** Gradio 6
renders server-side by default on Spaces, putting a Node proxy on the public port that
forwards only Gradio's own routes to Python behind it — the startup log says so:
`Running on local URL: http://0.0.0.0:7860, with SSR ⚡ (Node proxy -> Python :7861)`. The
Space answered `/api/meta` with Gradio's page *after* the API mount had been added and had
logged its own startup. `space_app.py` sets `GRADIO_SSR_MODE=false` before importing Gradio,
by assignment, since the platform sets it true.

**The interface on the Space is Gradio's.** The project's own interface is the Next.js
application in this repository, shown in the screenshots. Serving it from a Space works —
disable SSR, replace Gradio's index route, mount the export — but that is a lot of machinery
riding on two undocumented platform behaviours, for a demo. The pipeline behind both is the
same, and the API is mounted under `/api` so `POST /api/ask` returns the citations, their
verification status and the amendments behind them as JSON.

### Dependencies

`deploy/space/requirements.txt` lists **direct dependencies with floors, not a lockfile
export**. Hugging Face installs it in the same pip invocation as its own pins:

```
pip install -r requirements.txt "torch<=2.13.0" gradio[oauth,mcp]==6.27.0 \
    "uvicorn>=0.14.0" "websockets>=10.4" spaces==0.51.3
```

An exact transitive tree asks pip to satisfy our resolution and theirs at once, and there
is usually no such set. The first build failed on precisely that: our lock pinned
`pydantic==2.13.5` while gradio 6.27.0 requires `<=2.12.5`. Floors let pip find a set that
satisfies both — verified by resolving the combination for linux/Python 3.12 before
pushing.

`gradio` itself is deliberately absent from the file: the platform pins its own version,
and a second pin is a conflict waiting to happen.

Regenerate after changing backend dependencies:

```bash
./deploy/space/refresh.sh
```

### 2. Push

```bash
./deploy/push-to-space.sh <hf-username> <space-name>
```

It assembles everything in a throwaway directory with its own fresh git repository. This
repository is never checked out, never branched and never modified.

That matters: an earlier version did the opposite — it force-added the gitignored corpus
onto a temporary branch *here* and then switched back, and git deleted `data/raw`,
`data/parsed` and the index from the working tree on the way out, because they were tracked
on the branch it left and absent on the one it arrived at. Staging elsewhere removes the
whole class of accident.

The Space gets a single commit, not this project's history. It has no use for the
screenshots and charts, and Hugging Face **rejects binary files that are not stored through
LFS/Xet** — which every PNG ever committed here would be. The result is 78 files and 3.9 MB
instead of 872 objects and 14.5 MB.

One binary does ship: the index vectors, `data/index/legal_aware_schedule/vectors.npy`. The
script tracks `*.npy` with git-lfs before committing, which is what Hugging Face requires.
The 3.7 MB Schedule II PDF is deliberately left behind — the parsed rows ship instead and
are what the application reads; the PDF stays in this repository as their provenance.

Git will ask for credentials: the username is your Hugging Face username and the password
is a **write** access token from
[huggingface.co/settings/tokens](https://huggingface.co/settings/tokens). A read token
cannot push.

The entrypoint is `space_app.py`, not `app.py`, deliberately: a module named `app` at the
repository root shadows the `app` package under `backend/`, and every `import app.x` would
resolve to the wrong file.

### 3. Add the key

In the Space's **Settings → Variables and secrets**, add a secret named `GROQ_API_KEY`.

Do this there, not in the repository. A key in a commit is a key you have to rotate, and it
stays in the history after you delete it.

## What the deployment cannot do

**It shares one free-tier daily token allowance.** At roughly 3,000 tokens a question that
is about sixty questions a day across everyone using the link. When it runs out the app
says so, in those words, and recovers on its own — the corpus, retrieval and the citation
checks are all local and unaffected. Repeat questions are served from an answer cache and
cost nothing.

**It sleeps when idle.** The first request after a quiet period waits for the container to
wake.

**There is no local-model fallback.** `qwen2.5:3b-instruct` needs Ollama and a machine to
run it on; a free Space has neither. The fallback exists for local development, and the
evaluation uses it as a second measurement track — it is not a redundancy for this
deployment.

## Verified locally

The Gradio entrypoint was run the way Spaces runs it before being documented as working:

- `/`, `/api/meta`, `/gradio` and `/gradio/` all answer 200
- `POST /api/ask` reaches the model with no embedding-model download — the preloaded
  hub-layout cache is found, which is the whole point of `preload_from_hub`
- the spent-quota path was exercised for real and returned the intended 503, naming what
  ran out and when it frees up, rather than a 502 with a provider stack trace
- the Gradio fallback at `/gradio/` renders the disclaimer, accepts a question and runs the
  same pipeline

The container was separately built for `linux/amd64` and exercised the same way; see below.

## Running the container locally

```bash
docker build -t crimlaw .
docker run --rm -p 7860:7860 -e GROQ_API_KEY="$GROQ_API_KEY" crimlaw
```

Then open <http://localhost:7860>. This is the same image the Space builds, so a failure
here is a failure there.
