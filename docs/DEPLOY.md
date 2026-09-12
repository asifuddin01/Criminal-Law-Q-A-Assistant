# Deploying

The application runs as a single container: the frontend is exported to static files and
served by the API process, so the page and the API share an origin. One process, one
port, and no cross-origin configuration to get wrong somewhere nobody can debug it.

## Hugging Face Spaces

**Why this host.** Free, no card, and Docker-based — which matters because this is a
Python API and a Next.js frontend, and a Node-only host would need the backend somewhere
else and a CORS setup between them.

### 1. Create the Space

At [huggingface.co/new-space](https://huggingface.co/new-space): pick **Docker** → **Blank**,
and note the name. Leave it public.

### 2. Push

```bash
./deploy/push-to-space.sh <hf-username> <space-name>
```

The corpus under `data/` is gitignored — it is fetched, not authored — so the script
force-adds the two directories the image needs onto a throwaway branch, along with a
README whose frontmatter tells Hugging Face to build the Dockerfile. `main` and the
working tree are untouched.

What ships: `data/raw` (6.4 MB, the act HTML and the Schedule II PDF) and
`data/index/legal_aware_schedule` (3.7 MB). Both stay under the 10 MB per-file limit, so
no LFS. The raw corpus is needed at runtime, not just to build the index — citation
validation checks quoted text against the act's own words.

### 3. Add the key

In the Space's **Settings → Variables and secrets**, add a secret named `GROQ_API_KEY`.

Do this in that page, not in the repository. A key in a commit is a key you have to
rotate, and it stays in the history after you delete it.

The first build takes several minutes: it installs tesseract for the image-input path and
pulls the embedding model into the image, so the first question a visitor asks is not the
slowest one they will ever see.

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

## Running the container locally

```bash
docker build -t crimlaw .
docker run --rm -p 7860:7860 -e GROQ_API_KEY="$GROQ_API_KEY" crimlaw
```

Then open <http://localhost:7860>. This is the same image the Space builds, so a failure
here is a failure there.
