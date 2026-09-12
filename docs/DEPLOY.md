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

A Space created on ZeroGPU cannot always be downgraded to CPU basic afterwards: Hugging Face
treats that as a downgrade and may require PRO. Choosing the hardware at creation avoids the
question entirely.

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
