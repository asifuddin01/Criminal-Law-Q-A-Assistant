#!/usr/bin/env bash
# Push this repository to a Hugging Face Space.
#
#   ./deploy/push-to-space.sh <hf-username> <space-name>
#
# The Space runs under the `gradio` SDK, which has no build step — so everything
# a Dockerfile would have produced during a build has to be produced here and
# committed: the exported frontend, the parsed Schedule II, the corpus and the
# index. All of it goes onto a throwaway branch, so the working tree and main are
# untouched.
#
# The API key is NOT handled here. Set it in the Space's own settings, under
# Settings -> Variables and secrets, as GROQ_API_KEY. A key committed to a repo
# is a key you have to rotate, and it stays in the history after you delete it.
set -euo pipefail

if [ $# -ne 2 ]; then
    echo "usage: $0 <hf-username> <space-name>" >&2
    exit 2
fi

USER_NAME="$1"
SPACE_NAME="$2"
REMOTE="https://huggingface.co/spaces/${USER_NAME}/${SPACE_NAME}"
BRANCH="space-deploy-$(date +%s)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -d data/index/legal_aware_schedule ] || [ ! -d data/raw ]; then
    echo "data/ is missing. Build it first:" >&2
    echo "  cd backend && uv run python -m app.ingest" >&2
    echo "  cd backend && uv run python -m app.retrieval.build --strategy legal_aware --act 75 --with-schedule" >&2
    exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
    echo "working tree is not clean; commit or stash first" >&2
    exit 1
fi

STARTING_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
cleanup() {
    git checkout --quiet "$STARTING_BRANCH" 2>/dev/null || true
    git branch -D "$BRANCH" >/dev/null 2>&1 || true
    rm -rf "$ROOT/backend/static"
}
trap cleanup EXIT

echo "==> exporting the frontend"
(cd frontend && npm run build >/dev/null)
rm -rf backend/static
cp -R frontend/out backend/static

echo "==> precomputing the Schedule II parse"
# 48 seconds of PDF parsing that would otherwise run on every cold start.
(cd backend && uv run python -m app.ingest.precompute)

echo "==> preparing $BRANCH"
git checkout --quiet -b "$BRANCH"

# What the Space needs at its root.
cp deploy/space/space_app.py deploy/space/requirements.txt deploy/space/packages.txt .
cp deploy/space-readme.md README.md
git add -f space_app.py requirements.txt packages.txt README.md

# Built and fetched artefacts, which main does not track.
git add -f backend/static data/raw data/index/legal_aware_schedule data/parsed

git commit --quiet -m "deploy: application, corpus, index and Space configuration"

echo "==> pushing to $REMOTE"
git remote remove space 2>/dev/null || true
git remote add space "$REMOTE"
git push --force space "$BRANCH:main"

echo
echo "Pushed. Now, once only:"
echo "  1. open ${REMOTE}/settings"
echo "  2. under 'Variables and secrets', add a secret named GROQ_API_KEY"
echo "  3. paste your key there — it is never committed and never leaves that page"
echo
echo "The first build installs tesseract and 61 Python packages; several minutes."
echo "Watch it at ${REMOTE}?logs=build"
