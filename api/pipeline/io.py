"""Small writers that produce byte-stable files, so a rebuild with no input change is a no-op in git."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any


def write_json_gz(path: Path, payload: Any) -> None:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    with open(path, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(raw)


def read_json_gz(path: Path) -> Any:
    with gzip.open(path, "rb") as fh:
        return json.loads(fh.read())
