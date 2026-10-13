"""Step 2. Read the NAIP aerial image and the 3DEP lidar surface for the pilot.

Both come from the Microsoft Planetary Computer, which needs no key: the
`planetary-computer` package signs each asset URL with a short-lived token.
The files are cloud-optimised GeoTIFFs, so rasterio reads only the window we
need rather than the whole 400 MB quarter quad.

Outputs, all in data/raw (git-ignored):
    naip.npz   red, green, blue, nir as uint8, resampled onto the pilot grid
    lidar.npz  first-return surface elevation and point classification, same grid

    python -m pipeline.fetch_imagery
"""

from __future__ import annotations

import json

import numpy as np
import planetary_computer
import pystac_client
import rasterio
import rasterio.windows
from numpy.typing import NDArray
from pyproj import Transformer
from rasterio.windows import from_bounds
from shapely.geometry import box

from .config import NAIP_COLLECTION, RAW, STAC_URL
from .grid import pilot_frame, pilot_grid


def open_catalog() -> pystac_client.Client:
    return pystac_client.Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)


def grid_points_in(crs: str) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Pixel-centre coordinates of the pilot grid, expressed in another CRS."""
    frame, grid = pilot_frame(), pilot_grid()
    xs, ys = grid.centres()
    gx, gy = np.meshgrid(xs, ys)
    lon, lat = frame.to_lonlat(gx, gy)
    to = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    px, py = to.transform(lon, lat)
    return np.asarray(px), np.asarray(py)


def read_onto_grid(href: str, bands: list[int]) -> tuple[NDArray[np.generic], NDArray[np.bool_], dict[str, object]]:
    """Read a window of a remote raster and sample it at every pilot grid cell centre.

    Returns the samples, a mask of the cells the raster actually covers, and a few facts.
    """
    with rasterio.open(href) as src:
        px, py = grid_points_in(src.crs.to_string())
        pad = 4 * abs(src.transform.a)
        window = from_bounds(px.min() - pad, py.min() - pad, px.max() + pad, py.max() + pad, src.transform).round_offsets().round_lengths()
        window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        data = src.read(bands, window=window)
        transform = src.window_transform(window)
        col = np.floor((px - transform.c) / transform.a).astype(np.int64)
        row = np.floor((py - transform.f) / transform.e).astype(np.int64)
        ok = (row >= 0) & (row < data.shape[1]) & (col >= 0) & (col < data.shape[2])
        out = np.zeros((len(bands), *px.shape), dtype=data.dtype)
        out[:, ok] = data[:, row[ok], col[ok]]
        epsg = src.crs.to_epsg()
        info: dict[str, object] = {
            "crs": f"EPSG:{epsg}" if epsg else "compound NAD83 / UTM zone 14N + NAVD88",
            "native_res_m": abs(src.transform.a),
            "window_shape": list(data.shape),
            "nodata": src.nodata,
        }
    return out, ok, info


def fetch_naip(catalog: pystac_client.Client, bbox: tuple[float, float, float, float]) -> dict[str, object]:
    """The newest NAIP acquisition, mosaicked across quarter quads where the pilot straddles them."""
    items = list(catalog.search(collections=[NAIP_COLLECTION], bbox=bbox).items())
    if not items:
        raise RuntimeError("no NAIP item covers the pilot")
    newest = max(it.properties["datetime"][:4] for it in items)
    wanted = box(*bbox)
    tiles = sorted(
        (it for it in items if it.properties["datetime"].startswith(newest)),
        key=lambda it: -wanted.intersection(box(*it.bbox)).area,
    )
    grid = pilot_grid()
    mosaic = np.zeros((4, *grid.shape), dtype=np.uint8)
    filled = np.zeros(grid.shape, dtype=bool)
    used: list[dict[str, object]] = []
    for item in tiles:
        if filled.all():
            break
        data, ok, info = read_onto_grid(item.assets["image"].href, [1, 2, 3, 4])
        take = ok & ~filled
        mosaic[:, take] = data[:, take]
        filled |= take
        used.append({"item": item.id, "datetime": item.properties["datetime"], "gsd_m": item.properties.get("gsd"), "cells": int(take.sum()), **info})
    np.savez_compressed(RAW / "naip.npz", red=mosaic[0], green=mosaic[1], blue=mosaic[2], nir=mosaic[3], covered=filled)
    meta: dict[str, object] = {"tiles": used, "covered_share": round(float(filled.mean()), 4)}
    print("  naip:", json.dumps(meta))
    return meta


def fetch_lidar(catalog: pystac_client.Client, bbox: tuple[float, float, float, float]) -> dict[str, object] | None:
    """3DEP first-return surface (2 m) and classification. Optional: the model falls back to 8 m trees."""
    found: dict[str, object] = {}
    arrays: dict[str, NDArray[np.generic]] = {}
    for key, collection in (("dsm", "3dep-lidar-dsm"), ("classification", "3dep-lidar-classification")):
        items = list(catalog.search(collections=[collection], bbox=bbox).items())
        if not items:
            print(f"  lidar: no {collection} item here")
            return None
        item = items[0]
        data, ok, info = read_onto_grid(item.assets["data"].href, [1])
        arrays[key] = data[0]
        info["covered_share"] = round(float(ok.mean()), 4)
        found[key] = {"item": item.id, "datetime": item.properties.get("datetime") or item.properties.get("start_datetime"), **info}
    np.savez_compressed(RAW / "lidar.npz", **arrays)
    print("  lidar:", json.dumps(found))
    return found


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    frame, grid = pilot_frame(), pilot_grid()
    lon, lat = frame.to_lonlat(np.array([grid.x_min, grid.x_max]), np.array([grid.y_min, grid.y_max]))
    bbox = (float(lon[0]), float(lat[0]), float(lon[1]), float(lat[1]))
    print(f"grid {grid.width} x {grid.height} at {grid.res} m, bbox {tuple(round(v, 5) for v in bbox)}")
    catalog = open_catalog()
    meta: dict[str, object] = {"naip": fetch_naip(catalog, bbox)}
    try:
        meta["lidar"] = fetch_lidar(catalog, bbox)
    except Exception as exc:  # optional input, never fatal
        print(f"  lidar: unavailable ({type(exc).__name__}: {exc})")
        meta["lidar"] = None
    (RAW / "imagery.json").write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
