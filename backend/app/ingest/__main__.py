"""CLI entry point: python -m app.ingest [act_ids...] [--force]"""

import sys

from app.ingest.fetch import main

if __name__ == "__main__":
    sys.exit(main())
