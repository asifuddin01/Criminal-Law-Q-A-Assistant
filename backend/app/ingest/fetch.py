"""Cached retrieval of source documents from bdlaws.

Documents are cached on disk on first fetch. The corpus is a few hundred kilobytes
per act and is republished rarely, so repeated pipeline runs during development have
no business repeatedly hitting a government server.

Cached files are not committed: the pipeline must be reproducible from source, and
committing scraped artefacts would hide breakage in it.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys

import httpx

BASE_URL = "https://bdlaws.minlaw.gov.bd"
USER_AGENT = "criminal-law-qa/0.1 (academic assessment; contact via repository)"

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "data" / "raw"


def act_print_url(act_id: int) -> str:
    """The single-document print view for an act. See ADR 0005."""
    return f"{BASE_URL}/act-print-{act_id}.html"


def cache_path(act_id: int) -> pathlib.Path:
    return RAW_DIR / f"act-print-{act_id}.html"


def fetch_act(
    act_id: int, *, force: bool = False, timeout: float = 120.0
) -> pathlib.Path:
    """Fetch an act's print view, returning the path to the cached copy."""
    destination = cache_path(act_id)
    if destination.exists() and not force:
        return destination

    url = act_print_url(act_id)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(
        timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        response = client.get(url)
        response.raise_for_status()

    # Write via a temporary file so an interrupted fetch cannot leave a truncated
    # document that later parses into a plausible but incomplete act.
    temporary = destination.with_suffix(".partial")
    temporary.write_bytes(response.content)
    temporary.replace(destination)
    return destination


def source_hash(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch an act from bdlaws.")
    parser.add_argument(
        "act_ids",
        nargs="*",
        type=int,
        default=[75],
        help="bdlaws act ids (default: 75, the Code of Criminal Procedure, 1898)",
    )
    parser.add_argument(
        "--force", action="store_true", help="re-fetch even if already cached"
    )
    args = parser.parse_args(argv)

    for act_id in args.act_ids:
        cached = cache_path(act_id).exists()
        path = fetch_act(act_id, force=args.force)
        state = "cached" if cached and not args.force else "fetched"
        size = path.stat().st_size
        print(f"{state}: act-{act_id} -> {path} ({size:,} bytes)")
        print(f"  sha256: {source_hash(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
