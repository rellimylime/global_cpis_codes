"""
extract_confirmed_features.py
------------------------------
Extract candidate-style features at the locations of confirmed detection polygons,
bypassing the Hough/NMS candidate generation step entirely.

Inputs
------
--confirmed-polygons   .gpkg/.shp with confirmed CPI polygons (must have area_ha column)
--imagery-dir          directory containing *_rgbnir_u8.tif chips
--year                 integer year label for the training table (default: 2021)

Outputs
-------
--out-csv              path for output CSV (training-ready rows, label=1)

The output columns match the training table schema:
  tile_id, year, x, y, center_lon, center_lat, radius_px, radius_m,
  geom_score, ndvi_amp, ndwi_p50_center, ring_contrast, texture_score,
  pixel_size_m, label
"""

import argparse
import math
import sys
from pathlib import Path

import cv2
import geopandas as gpd
import numpy as np
import pandas as pd
from osgeo import gdal

# ── allow import from src/ ──────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cpis.common.geo_utils import raster_pixel_size_m


# ── feature helpers (mirrors generate_candidates.py) ────────────────────────

def _extract_score_raster(arr: np.ndarray) -> np.ndarray:
    """Return a 2-D float32 NDVI/score raster from a multi-band array."""
    if arr.shape[0] >= 10:
        return arr[9].astype(np.float32)
    if arr.shape[0] >= 4:
        red = arr[2].astype(np.float32)
        nir = arr[3].astype(np.float32)
        den = np.maximum(1e-6, nir + red)
        return (nir - red) / den
    return arr[0].astype(np.float32)


def _norm_u8(img: np.ndarray) -> np.ndarray:
    mn, mx = float(np.nanmin(img)), float(np.nanmax(img))
    if mx - mn < 1e-9:
        return np.zeros(img.shape, dtype=np.uint8)
    return np.clip((img - mn) / (mx - mn) * 255, 0, 255).astype(np.uint8)


def _annulus_stats(score: np.ndarray, cx: float, cy: float, r: float):
    h, w = score.shape
    rr = max(2.0, r)
    pad = int(np.ceil(1.25 * rr))
    x0 = max(0, int(np.floor(cx)) - pad)
    x1 = min(w, int(np.floor(cx)) + pad + 1)
    y0 = max(0, int(np.floor(cy)) - pad)
    y1 = min(h, int(np.floor(cy)) + pad + 1)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return 0.0, 0.0
    patch = score[y0:y1, x0:x1]
    yg, xg = np.ogrid[y0:y1, x0:x1]
    dist = np.sqrt((xg - cx) ** 2 + (yg - cy) ** 2)
    inner = dist <= 0.8 * rr
    annulus = (dist >= 0.9 * rr) & (dist <= 1.2 * rr)
    if not inner.any() or not annulus.any():
        return 0.0, 0.0
    ring_contrast = abs(float(np.nanmean(patch[annulus])) - float(np.nanmean(patch[inner])))
    texture = float(np.nanstd(patch[annulus]))
    return ring_contrast, texture


def _edge_support(edges: np.ndarray, cx: float, cy: float, r: float, n: int = 96) -> float:
    h, w = edges.shape
    hits = total = 0
    for theta in np.linspace(0.0, 2 * math.pi, n, endpoint=False):
        xi = int(round(cx + r * math.cos(theta)))
        yi = int(round(cy + r * math.sin(theta)))
        if 0 <= xi < w and 0 <= yi < h:
            total += 1
            if edges[yi, xi] > 0:
                hits += 1
    return hits / total if total else 0.0


# ── raster cache (open each chip once) ──────────────────────────────────────

class _RasterCache:
    def __init__(self):
        self._cache: dict[str, tuple] = {}

    def get(self, path: Path):
        key = str(path)
        if key not in self._cache:
            ds = gdal.Open(key)
            if ds is None:
                raise RuntimeError(f"Could not open raster: {path}")
            arr = ds.ReadAsArray()
            if arr.ndim == 2:
                arr = arr[np.newaxis]
            px_m = raster_pixel_size_m(ds)
            gt = ds.GetGeoTransform()   # (lon_origin, px_lon, 0, lat_origin, 0, px_lat)
            score = _extract_score_raster(arr)
            score_u8 = _norm_u8(score)
            blur = cv2.GaussianBlur(score_u8, (5, 5), 1.2)
            edges = cv2.Canny(blur, 30, 90)
            self._cache[key] = (arr, score, blur, edges, px_m, gt)
        return self._cache[key]


def _lonlat_to_px(lon: float, lat: float, gt) -> tuple[float, float]:
    """Convert geographic lon/lat to raster pixel (x, y) using geotransform."""
    # gt = (x_origin, px_w, rot_x, y_origin, rot_y, px_h)
    # lon = x_origin + x*px_w + y*rot_x  →  x ≈ (lon - x_origin) / px_w
    # lat = y_origin + x*rot_y + y*px_h  →  y ≈ (lat - y_origin) / px_h
    x = (lon - gt[0]) / gt[1]
    y = (lat - gt[3]) / gt[5]
    return x, y


def _find_chip(lon: float, lat: float, chips: list[tuple]) -> tuple | None:
    """Return (path, arr, score, blur, edges, px_m, gt) for the chip covering (lon, lat)."""
    for path, arr, score, blur, edges, px_m, gt in chips:
        w = arr.shape[2]
        h = arr.shape[1]
        x, y = _lonlat_to_px(lon, lat, gt)
        if 0 <= x < w and 0 <= y < h:
            return path, arr, score, blur, edges, px_m, gt
    return None


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--confirmed-polygons", required=True)
    ap.add_argument("--imagery-dir", required=True)
    ap.add_argument("--year", type=int, default=2021)
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--canny-low", type=int, default=30)
    ap.add_argument("--canny-high", type=int, default=90)
    args = ap.parse_args()

    # Load confirmed detections
    gdf = gpd.read_file(args.confirmed_polygons)
    print(f"Loaded {len(gdf)} confirmed polygons")

    # Compute centroids in geographic CRS
    utm = gdf.to_crs("EPSG:32735")
    utm["_area_m2"] = utm.geometry.area
    utm["_radius_m"] = np.sqrt(utm["_area_m2"] / np.pi)
    gdf = gdf.copy()
    gdf["_radius_m"] = utm["_radius_m"].values
    gdf_wgs = gdf.to_crs("EPSG:4326")
    gdf_wgs["_cx_lon"] = gdf_wgs.geometry.centroid.x
    gdf_wgs["_cy_lat"] = gdf_wgs.geometry.centroid.y

    # Discover chips (read geotransform only, do NOT load raster data yet)
    imagery_dir = Path(args.imagery_dir)
    tif_paths = sorted(imagery_dir.glob("*.tif"))
    if not tif_paths:
        raise RuntimeError(f"No .tif files found in {imagery_dir}")
    print(f"Found {len(tif_paths)} imagery chips")

    def _chip_gt(path: Path):
        ds = gdal.Open(str(path))
        if ds is None:
            return None
        gt = ds.GetGeoTransform()
        w, h = ds.RasterXSize, ds.RasterYSize
        ds = None
        return gt, w, h

    chip_meta = {}  # path -> (gt, w, h)
    for p in tif_paths:
        meta = _chip_gt(p)
        if meta:
            chip_meta[p] = meta

    def _find_chip_path(lon, lat):
        for p, (gt, w, h) in chip_meta.items():
            x, y = _lonlat_to_px(lon, lat, gt)
            if 0 <= x < w and 0 <= y < h:
                return p, gt
        return None, None

    # Group detections by chip (so we load each chip at most once)
    assignments: dict[Path, list] = {}
    unassigned = []
    for idx, row in gdf_wgs.iterrows():
        lon, lat = row["_cx_lon"], row["_cy_lat"]
        p, gt = _find_chip_path(lon, lat)
        if p is None:
            unassigned.append((lon, lat))
        else:
            assignments.setdefault(p, []).append(row)

    for lon, lat in unassigned:
        print(f"[warn] No chip covers ({lon:.4f}, {lat:.4f}), skipping")

    # Extract features chip-by-chip (one chip in memory at a time)
    rows = []
    skipped = len(unassigned)
    for chip_path, det_rows in assignments.items():
        print(f"  Loading chip {chip_path.name} ({len(det_rows)} detections) …")
        arr, score, blur, edges, px_m, gt = _RasterCache().get(chip_path)
        h, w = arr.shape[1], arr.shape[2]
        for row in det_rows:
            lon = row["_cx_lon"]
            lat = row["_cy_lat"]
            radius_m = row["_radius_m"]
            cx, cy = _lonlat_to_px(lon, lat, gt)
            radius_px = radius_m / px_m

            if not (0 <= cx < w and 0 <= cy < h):
                skipped += 1
                continue

            ring_contrast, texture = _annulus_stats(score, cx, cy, radius_px)
            geom_score = _edge_support(edges, cx, cy, radius_px)
            ndvi_center = float(np.nanmean(
                score[max(0, int(cy) - 2): int(cy) + 3, max(0, int(cx) - 2): int(cx) + 3]
            ))

            # NDWI center (band 10 if available)
            ndwi_center = None
            if arr.shape[0] >= 11:
                ndwi_band = arr[10].astype(np.float32)
                ndwi_center = float(np.nanmean(
                    ndwi_band[max(0, int(cy) - 2): int(cy) + 3, max(0, int(cx) - 2): int(cx) + 3]
                ))

            tile_id = chip_path.stem
            rows.append({
                "tile_id": tile_id,
                "year": args.year,
                "x": float(cx),
                "y": float(cy),
                "center_lon": lon,
                "center_lat": lat,
                "radius_px": radius_px,
                "radius_m": radius_m,
                "geom_score": geom_score,
                "ndvi_amp": ndvi_center,
                "ndwi_p50_center": ndwi_center,
                "ring_contrast": ring_contrast,
                "texture_score": texture,
                "pixel_size_m": px_m,
                "label": 1,
            })

    print(f"Extracted features for {len(rows)} confirmed detections ({skipped} skipped / no chip)")

    out_path = Path(args.out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
