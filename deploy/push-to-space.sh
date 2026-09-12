#!/usr/bin/env bash
# Push this project to a Hugging Face Space.
#
#   ./deploy/push-to-space.sh <hf-username> <space-name>
#
# Everything is assembled in a throwaway directory with its own fresh git repo.
# This repository is never checked out, never branched and never modified.
#
# An earlier version of this script did the opposite: it force-added the
# gitignored corpus onto a temporary branch in *this* repo and then switched
# back. Git dutifully deleted data/raw, data/parsed and the index from the
# working tree on the way out, because they were tracked on the branch it left
# and absent on the one it arrived at. Staging elsewhere removes the whole class
# of accident.
#
# The Space also gets a single commit rather than this project's history. It has
# no use for eighteen months of screenshots, and Hugging Face rejects binaries
# that are not stored through LFS/Xet — including every PNG ever committed here.
#
# The API key is NOT handled here. Set it in the Space's own settings, under
# Settings -> Variables and secrets, as GROQ_API_KEY. A key in a commit is a key
# you have to rotate, and it stays in the history after you delete it.
set -euo pipefail

if [ $# -ne 2 ]; then
    echo "usage: $0 <hf-username> <space-name>" >&2
    exit 2
fi

USER_NAME="$1"
SPACE_NAME="$2"
REMOTE="https://huggingface.co/spaces/${USER_NAME}/${SPACE_NAME}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v git-lfs >/dev/null 2>&1; then
    echo "git-lfs is required (the index is a binary file): brew install git-lfs" >&2
    exit 1
fi

if [ ! -d data/index/legal_aware_schedule ] || [ ! -d data/raw ]; then
    echo "data/ is missing. Build it first:" >&2
    echo "  cd backend && uv run python -m app.ingest" >&2
    echo "  cd backend && uv run python -m app.retrieval.build --strategy legal_aware --act 75 --with-schedule" >&2
    exit 1
fi

STAGE="$(mktemp -d -t crimlaw-space)"
trap 'rm -rf "$STAGE"' EXIT

# The Space README's YAML is validated by a pre-receive hook, so a field that is
# one character too long costs a full build-and-push round trip to discover.
# Check it here, where it costs nothing.
echo "==> checking the Space README metadata"
python3 - "$ROOT/deploy/space-readme.md" <<'PYCHECK'
import pathlib
import sys

LIMITS = {"short_description": 60, "title": 100}
REQUIRED = ("title", "sdk", "app_file")

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
if not text.startswith("---\n"):
    sys.exit("space-readme.md does not begin with a YAML front-matter block")

block = text.split("---\n", 2)[1]
fields = {}
for line in block.splitlines():
    if line[:1].isalpha() and ":" in line:
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()

problems = []
for key in REQUIRED:
    if key not in fields:
        problems.append(f"{key} is missing")
for key, limit in LIMITS.items():
    value = fields.get(key, "")
    if len(value) > limit:
        problems.append(f"{key} is {len(value)} characters, limit is {limit}: {value!r}")

if problems:
    sys.exit("Space README metadata will be rejected:\n  - " + "\n  - ".join(problems))
print(f"    ok — sdk={fields.get('sdk')} app_file={fields.get('app_file')} "
      f"short_description={len(fields.get('short_description', ''))} chars")
PYCHECK

# Invariants the deployment depends on and nothing else imports: the GPU
# declaration ZeroGPU demands, SSR disabled, the API mounted rather than
# included. Each corresponds to a Space that failed to start, and the last one
# reached the platform because these were checked by a test nobody ran before
# uploading. A hundredth of a second here.
echo "==> checking the Space entrypoint"
(cd backend && uv run pytest tests/test_space_entrypoint.py -q --no-header 2>&1 | tail -1)
(cd backend && uv run pytest tests/test_space_entrypoint.py -q >/dev/null 2>&1) || {
    echo "the Space entrypoint is not deployable; not pushing" >&2
    exit 1
}

echo "==> precomputing the Schedule II parse"
# 48 seconds of PDF parsing that would otherwise run on every cold start, and a
# Gradio Space has no build step in which to do it.
(cd backend && uv run python -m app.ingest.precompute >/dev/null)

echo "==> assembling the Space in $STAGE"
mkdir -p "$STAGE/backend" "$STAGE/data/raw" "$STAGE/data/parsed" "$STAGE/data/index"

# The application, minus everything that is not needed to serve it.
rsync -a --quiet \
    --exclude '__pycache__' --exclude '.venv' --exclude '.pytest_cache' \
    --exclude '.ruff_cache' --exclude 'tests' --exclude 'static' --exclude '.env*' \
    --exclude 'evaluation' \
    backend/ "$STAGE/backend/"

# The corpus. The Schedule II PDF is deliberately not shipped: the parsed rows
# are, the application reads those, and the PDF is 3.7 MB of binary that would
# only be re-parsed. It stays in this repository as the provenance for them.
cp data/raw/act-print-*.html "$STAGE/data/raw/"
cp data/parsed/schedule-ii.json "$STAGE/data/parsed/"
cp -R data/index/legal_aware_schedule "$STAGE/data/index/"

# What the Space itself needs at its root.
cp deploy/space/space_app.py deploy/space/requirements.txt deploy/space/packages.txt "$STAGE/"
cp deploy/space-readme.md "$STAGE/README.md"

cd "$STAGE"
git init -q -b main
git lfs install --local >/dev/null

# Hugging Face rejects binary files committed as plain git blobs. The index
# vectors are the only binary here; tracking the extension rather than the path
# keeps this correct if another index is ever added.
git lfs track "*.npy" >/dev/null
git add .gitattributes

git add -A
git -c user.email="deploy@localhost" -c user.name="deploy" \
    commit -q -m "Criminal Law Q&A — application, corpus and index"

echo "==> pushing to $REMOTE"
git remote add space "$REMOTE"
git push --force space main

echo
echo "Pushed. Now, once only:"
echo "  1. open ${REMOTE}/settings"
echo "  2. under 'Variables and secrets', add a secret named GROQ_API_KEY"
echo "  3. paste your key there — it is never committed and never leaves that page"
echo
echo "Watch the build at ${REMOTE}?logs=build"
