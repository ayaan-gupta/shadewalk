"""A minimal PNG encoder, so the API needs no imaging library.

Two writers: indexed colour with per-entry alpha (the shadow overlay, a few
kilobytes for the whole pilot) and plain 8-bit RGB (debug images in the pipeline).
"""

from __future__ import annotations

import struct
import zlib

import numpy as np
from numpy.typing import NDArray

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def _scanlines(rows: NDArray[np.uint8]) -> bytes:
    """Prefix every row with filter type 0 and deflate."""
    height = rows.shape[0]
    flat = rows.reshape(height, -1)
    out = np.zeros((height, flat.shape[1] + 1), dtype=np.uint8)
    out[:, 1:] = flat
    return zlib.compress(out.tobytes(), 9)


def encode_indexed(index: NDArray[np.uint8], palette: list[tuple[int, int, int, int]]) -> bytes:
    """Encode a 2-D array of palette indices. Palette entries are (r, g, b, a)."""
    if index.ndim != 2:
        raise ValueError("index must be 2-D")
    if not 1 <= len(palette) <= 256:
        raise ValueError("palette must have 1 to 256 entries")
    height, width = index.shape
    header = struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0)
    plte = b"".join(bytes(entry[:3]) for entry in palette)
    trns = bytes(entry[3] for entry in palette)
    return (
        SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"PLTE", plte)
        + _chunk(b"tRNS", trns)
        + _chunk(b"IDAT", _scanlines(np.ascontiguousarray(index, dtype=np.uint8)))
        + _chunk(b"IEND", b"")
    )


def encode_rgb(rgb: NDArray[np.uint8]) -> bytes:
    """Encode an (H, W, 3) uint8 array."""
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must be (H, W, 3)")
    height, width, _ = rgb.shape
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", _scanlines(np.ascontiguousarray(rgb, dtype=np.uint8))) + _chunk(b"IEND", b"")
