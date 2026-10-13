"""Load the committed pilot dataset into PostGIS.

    DATABASE_URL=postgresql://... python -m shadewalk.store.seed [--force]
"""

from __future__ import annotations

import argparse
import time

from ..config import get_settings
from .postgis import seed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="reload even if the database already matches the files")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set")
    started = time.time()
    changed = seed(settings.database_url, settings.data_dir, force=args.force)
    print(f"PostGIS {'seeded' if changed else 'already current'} in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
