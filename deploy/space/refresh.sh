#!/usr/bin/env bash
# Regenerate the Space's requirements.txt from backend/pyproject.toml.
#
# Direct dependencies with their floors — deliberately NOT a lockfile export.
#
# Hugging Face installs this file in the same pip invocation as its own pins:
#
#   pip install -r requirements.txt "torch<=2.13.0" \
#       gradio[oauth,mcp]==6.27.0 "uvicorn>=0.14.0" \
#       "websockets>=10.4" spaces==0.51.3
#
# A fully pinned transitive tree — sixty-odd packages at == — asks pip to satisfy
# our exact resolution and theirs at once, and there is usually no such set.
# Floors let pip find one that satisfies both.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

python3 - "$ROOT" <<'PYGEN'
import pathlib
import sys
import tomllib

root = pathlib.Path(sys.argv[1])
pyproject = tomllib.loads((root / "backend" / "pyproject.toml").read_text("utf-8"))
deps = pyproject["project"]["dependencies"]

out = root / "deploy" / "space" / "requirements.txt"
out.write_text(
    "# Generated from backend/pyproject.toml by deploy/space/refresh.sh.\n"
    "# Direct dependencies with floors, not a lockfile export: Hugging Face\n"
    "# installs this in the same pip invocation as its own pins for gradio,\n"
    "# torch and spaces, and an exact transitive tree leaves pip no solution.\n"
    "# gradio itself is deliberately absent — the platform pins its own.\n"
    + "\n".join(deps)
    + "\n",
    encoding="utf-8",
)
print(f"wrote {out.relative_to(root)} ({len(deps)} direct dependencies)")
PYGEN
