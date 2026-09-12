#!/usr/bin/env bash
# Regenerate the Space's pinned requirements from backend/uv.lock.
#
# A Gradio Space installs from requirements.txt and has no lockfile support, so
# the resolved set is committed. Run this after changing backend dependencies.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT/backend"
{
    echo "# Generated from backend/uv.lock by deploy/space/refresh.sh — do not hand-edit."
    echo "# A Gradio Space has no build step, so the pinned set is committed rather than resolved."
    uv export --frozen --no-dev --no-emit-project --no-hashes --format requirements-txt \
        | grep -vE '^\s*#|^$'
} > "$ROOT/deploy/space/requirements.txt"
echo "wrote deploy/space/requirements.txt ($(grep -c '==' "$ROOT/deploy/space/requirements.txt") packages)"
