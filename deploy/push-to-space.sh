#!/usr/bin/env bash
# Push this repository to a Hugging Face Space.
#
#   ./deploy/push-to-space.sh <hf-username> <space-name>
#
# The Space needs two things this repository does not track: the corpus under
# data/, which is gitignored because it is fetched rather than authored, and a
# README whose frontmatter tells Hugging Face to build the Dockerfile. Both are
# assembled on a throwaway branch so the working tree and main are untouched.
#
# The API key is NOT handled here. Set it in the Space's own settings, under
# Settings -> Variables and secrets, as GROQ_API_KEY. A key committed to a repo
# is a key you have to rotate.
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
}
trap cleanup EXIT

echo "==> preparing $BRANCH"
git checkout --quiet -b "$BRANCH"

# The corpus and the one index the deployment serves from.
git add -f data/raw data/index/legal_aware_schedule

# Hugging Face reads the Space configuration from README frontmatter, so the
# Space gets its own README. The repository's stays as it is on main.
cp deploy/space-readme.md README.md
git add README.md

git commit --quiet -m "deploy: corpus, index and Space configuration"

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
echo "The first build takes several minutes; it installs tesseract and bakes the"
echo "embedding model into the image so the first question is not the slowest."
echo "Watch it at ${REMOTE}?logs=build"
