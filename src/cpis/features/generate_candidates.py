"""Generate circle candidates from Landsat composite tiles."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd
from osgeo import gdal

from cpis.common.file_utils import ensure_dir, file_sig, save_json
from cpis.common.geo_utils import circle_overlap_ratio, raster_pixel_size_m, raster_xy_to_wgs84
from cpis.common.region_filter import RegionMask
from cpis.common.lock_utils import manifest_lock
from cpis.common.logging_utils import build_logger
from cpis.common.manifest import load_manifest, save_manifest, tile_status_counts
from cpis.common.time_utils import utc_now_iso

gdal.UseExceptions()


def _norm_u8(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float32)
    valid = np.isfinite(arr)
    if not valid.any():
        return np.zeros(arr.shape, dtype=np.uint8)
    lo, hi = np.percentile(arr[valid], [2, 98])
    if hi <= lo:
        hi = lo + 1.0
    out = np.zeros(arr.shape, dtype=np.float32)
    out[valid] = (arr[valid] - lo) / (hi - lo)
    out = np.clip(out, 0.0, 1.0)
    out = np.nan_to_num(out, nan=0.0, posinf=1.0, neginf=0.0)
    return (out * 255.0).astype(np.uint8)


def _extract_score_raster(arr_bands: np.ndarray) -> np.ndarray:
    # Preferred 11-band layout from export_year.py:
    # blue_median,green_median,red_median,nir_median,swir1_median,swir2_median,ndvi_p10,ndvi_p50,ndvi_p90,ndvi_amp,ndwi_p50
    if arr_bands.shape[0] >= 10:
        return arr_bands[9].astype(np.float32)

    if arr_bands.shape[0] >= 4:
        red = arr_bands[2].astype(np.float32)
        nir = arr_bands[3].astype(np.float32)
        den = np.maximum(1e-6, nir + red)
        ndvi = (nir - red) / den
        return ndvi

    # Last resort fallback to first band.
    return arr_bands[0].astype(np.float32)


def _annulus_stats(score_img: np.ndarray, cx: float, cy: float, r: float) -> tuple[float, float]:
    h, w = score_img.shape
    rr = max(2.0, float(r))
    pad = int(np.ceil(1.25 * rr))
    x0 = max(0, int(np.floor(cx)) - pad)
    x1 = min(w, int(np.floor(cx)) + pad + 1)
    y0 = max(0, int(np.floor(cy)) - pad)
    y1 = min(h, int(np.floor(cy)) + pad + 1)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return 0.0, 0.0

    patch = score_img[y0:y1, x0:x1]
    y_grid, x_grid = np.ogrid[y0:y1, x0:x1]
    dist = np.sqrt((x_grid - cx) ** 2 + (y_grid - cy) ** 2)
    inner = dist <= (0.8 * rr)
    annulus = (dist >= (0.9 * rr)) & (dist <= (1.2 * rr))
    if not inner.any() or not annulus.any():
        return 0.0, 0.0
    m_inner = float(np.nanmean(patch[inner]))
    m_ring = float(np.nanmean(patch[annulus]))
    ring_contrast = abs(m_ring - m_inner)
    texture = float(np.nanstd(patch[annulus]))
    return ring_contrast, texture


def _edge_support(edges: np.ndarray, cx: float, cy: float, r: float, n_samples: int = 96) -> float:
    h, w = edges.shape
    hits = 0
    total = 0
    for theta in np.linspace(0.0, 2.0 * math.pi, num=n_samples, endpoint=False):
        x = int(round(cx + (r * math.cos(theta))))
        y = int(round(cy + (r * math.sin(theta))))
        if x < 0 or x >= w or y < 0 or y >= h:
            continue
        total += 1
        if edges[y, x] > 0:
            hits += 1
    return float(hits / total) if total > 0 else 0.0


def _circle_nms(candidates: list[dict[str, Any]], iou_thr: float = 0.35) -> list[dict[str, Any]]:
    if not candidates:
        return []
    order = sorted(
        candidates,
        key=lambda r: float(r["geom_score"]) + float(r["ring_contrast"]) + 0.25 * float(r["texture_score"]),
        reverse=True,
    )
    kept: list[dict[str, Any]] = []
    for row in order:
        keep = True
        for k in kept:
            iou = circle_overlap_ratio(
                float(row["x"]),
                float(row["y"]),
                float(row["radius_px"]),
                float(k["x"]),
                float(k["y"]),
                float(k["radius_px"]),
            )
            if iou >= iou_thr:
                keep = False
                break
        if keep:
            kept.append(row)
    return kept


def _process_tile(path: Path, args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ds = gdal.Open(str(path))
    if ds is None:
        raise RuntimeError(f"Could not open raster: {path}")

    arr = ds.ReadAsArray()
    if arr is None:
        raise RuntimeError(f"Could not read raster array: {path}")
    if arr.ndim == 2:
        arr = arr[np.newaxis, :, :]
    if arr.ndim != 3:
        raise RuntimeError(f"Unexpected raster shape {arr.shape}: {path}")

    score = _extract_score_raster(arr)
    ndwi = arr[10].astype(np.float32) if arr.shape[0] >= 11 else None
    score_u8 = _norm_u8(score)
    blur = cv2.GaussianBlur(score_u8, (5, 5), 1.2)
    edges = cv2.Canny(blur, threshold1=int(args.canny_low), threshold2=int(args.canny_high))

    px_m = raster_pixel_size_m(ds)
    min_r_px = max(3, int(round(float(args.min_radius_m) / px_m)))
    max_r_px = max(min_r_px + 2, int(round(float(args.max_radius_m) / px_m)))

    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=float(args.hough_dp),
        minDist=float(args.min_dist_px),
        param1=float(args.hough_param1),
        param2=float(args.hough_param2),
        minRadius=min_r_px,
        maxRadius=max_r_px,
    )

    tile_id = path.stem
    rows: list[dict[str, Any]] = []
    region_filtered = 0
    water_filtered = 0
    region_mask: RegionMask | None = getattr(args, "_region_mask_obj", None)
    if circles is not None and len(circles) > 0:
        circles_arr = circles[0]
        prepared: list[tuple[float, float, float, float | None, float | None]] = []
        for c in circles_arr:
            cx, cy, r = float(c[0]), float(c[1]), float(c[2])
            if r < min_r_px or r > max_r_px:
                continue
            if region_mask is not None:
                lon, lat = raster_xy_to_wgs84(ds, cx, cy)
                if not region_mask.contains(lon, lat):
                    region_filtered += 1
                    continue
                prepared.append((cx, cy, r, lon, lat))
            else:
                prepared.append((cx, cy, r, None, None))

        max_raw = int(args.max_raw_circles)
        if max_raw > 0 and len(prepared) > max_raw:
            prepared = prepared[:max_raw]

        for cx, cy, r, lon, lat in prepared:
            ring_contrast, texture = _annulus_stats(score, cx, cy, r)
            geom_score = _edge_support(edges, cx, cy, r, n_samples=96)
            if lon is None or lat is None:
                lon, lat = raster_xy_to_wgs84(ds, cx, cy)
            ndwi_center = float("nan")
            if ndwi is not None:
                ix = int(round(cx))
                iy = int(round(cy))
                if 0 <= ix < ndwi.shape[1] and 0 <= iy < ndwi.shape[0]:
                    ndwi_center = float(ndwi[iy, ix])
            if bool(getattr(args, "exclude_water", False)) and np.isfinite(ndwi_center):
                if ndwi_center >= float(getattr(args, "water_ndwi_threshold", 0.0)):
                    water_filtered += 1
                    continue
            rows.append(
                {
                    "year": int(args.year),
                    "tile_id": tile_id,
                    "tile_path": str(path.resolve()),
                    "x": cx,
                    "y": cy,
                    "center_lon": lon,
                    "center_lat": lat,
                    "radius_px": r,
                    "radius_m": float(r * px_m),
                    "geom_score": float(geom_score),
                    "ndvi_amp": float(np.nanmean(score[max(0, int(cy - 2)): int(cy + 3), max(0, int(cx - 2)): int(cx + 3)])),
                    "ndwi_p50_center": ndwi_center,
                    "ring_contrast": float(ring_contrast),
                    "texture_score": float(texture),
                    "pixel_size_m": float(px_m),
                    "source_model": "circle_hough_v1",
                }
            )

    rows = _circle_nms(rows, iou_thr=float(args.nms_iou))
    rows = rows[: int(args.max_candidates_per_tile)]
    stats = {
        "tile_id": tile_id,
        "tile_path": str(path.resolve()),
        "shape": [int(ds.RasterYSize), int(ds.RasterXSize)],
        "pixel_size_m": float(px_m),
        "ndwi_available": bool(ndwi is not None),
        "raw_circle_count": int(0 if circles is None else len(circles[0])),
        "region_filtered_count": int(region_filtered),
        "water_filtered_count": int(water_filtered),
        "candidate_count": int(len(rows)),
    }
    return rows, stats


def _load_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _write_candidates(df: pd.DataFrame, out_parquet: Path, out_csv: Path, log) -> str:
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fmt = "parquet"
    try:
        df.to_parquet(out_parquet, index=False)
        log(f"Wrote candidates parquet: {out_parquet}")
    except Exception as exc:
        fmt = "csv"
        log(f"[warn] parquet write failed ({exc}); writing CSV fallback")
    df.to_csv(out_csv, index=False)
    return fmt


def run_generate_candidates(args: argparse.Namespace) -> int:
    in_dir = Path(args.input_dir)
    if not in_dir.exists():
        raise FileNotFoundError(f"Input dir not found: {in_dir}")
    tif_list = sorted([p for p in in_dir.rglob("*.tif") if p.is_file()])
    if not tif_list:
        raise RuntimeError(f"No .tif files found in {in_dir}")

    if int(args.max_tiles) > 0:
        tif_list = tif_list[: int(args.max_tiles)]

    out_dir = Path(args.out_dir) if args.out_dir else Path("runs") / "features" / str(args.year)
    ensure_dir(out_dir)
    per_tile_dir = ensure_dir(out_dir / "tiles")
    out_parquet = out_dir / "candidates.parquet"
    out_csv = out_dir / "candidates.csv"
    manifest_path = Path(args.manifest) if args.manifest else (out_dir / "feature_manifest.json")
    log = build_logger(args.log_file if args.log_file else out_dir / "feature_generation.log")

    manifest = load_manifest(
        manifest_path,
        {
            "version": 1,
            "year": int(args.year),
            "input_dir": str(in_dir.resolve()),
            "tiles": {},
            "candidates_path": str(out_parquet.resolve()),
        },
    )
    manifest.setdefault("tiles", {})

    region_mask_obj: RegionMask | None = None
    region_mask_arg = str(getattr(args, "region_mask", "")).strip()
    if region_mask_arg:
        region_path = Path(region_mask_arg)
        region_mask_obj = RegionMask.from_geojson(region_path)
        log(
            "Loaded region mask: "
            f"{region_path.resolve()} polygons={region_mask_obj.polygon_count} "
            f"bounds={region_mask_obj.bounds}"
        )
    setattr(args, "_region_mask_obj", region_mask_obj)

    existing_df: pd.DataFrame | None = None
    if args.resume and out_parquet.exists():
        try:
            existing_df = _load_table(out_parquet)
        except Exception:
            existing_df = None

    all_rows: list[dict[str, Any]] = []
    if existing_df is not None and len(existing_df) > 0:
        all_rows.extend(existing_df.to_dict(orient="records"))
        log(f"Loaded existing candidates rows: {len(existing_df)}")

    processed = 0
    failed = 0
    lock_path = out_dir / ".feature_manifest.lock.json"
    with manifest_lock(
        lock_path=lock_path,
        stale_seconds=int(args.stale_lock_seconds),
        force=bool(args.force_lock),
    ):
        for i, tif in enumerate(tif_list, start=1):
            tile_id = tif.stem
            sig = file_sig(tif)
            state = manifest["tiles"].get(tile_id, {})
            if args.resume and state.get("status") == "succeeded" and state.get("sig") == sig:
                log(f"[{i}/{len(tif_list)}] skip {tile_id} (resume hit)")
                continue

            log(f"[{i}/{len(tif_list)}] process {tile_id}")
            started = utc_now_iso()
            row_state = {
                "tile_id": tile_id,
                "status": "running",
                "sig": sig,
                "started_at": started,
                "ended_at": None,
                "candidate_count": 0,
                "error": "",
            }
            manifest["tiles"][tile_id] = row_state
            save_manifest(manifest_path, manifest)

            try:
                rows, stats = _process_tile(tif, args)
                # Remove stale rows for this tile before inserting the fresh ones.
                all_rows = [r for r in all_rows if str(r.get("tile_id")) != tile_id]
                all_rows.extend(rows)
                save_json(per_tile_dir / f"{tile_id}.json", stats)

                row_state["status"] = "succeeded"
                row_state["candidate_count"] = int(len(rows))
                row_state["ended_at"] = utc_now_iso()
                processed += 1
            except Exception as exc:
                row_state["status"] = "failed"
                row_state["error"] = str(exc)
                row_state["ended_at"] = utc_now_iso()
                failed += 1
                log(f"[error] {tile_id}: {exc}")
            finally:
                manifest["tiles"][tile_id] = row_state
                save_manifest(manifest_path, manifest)

    if all_rows:
        df = pd.DataFrame(all_rows).sort_values(["tile_id", "geom_score"], ascending=[True, False])
    else:
        df = pd.DataFrame(
            columns=[
                "year",
                "tile_id",
                "tile_path",
                "x",
                "y",
                "center_lon",
                "center_lat",
                "radius_px",
                "radius_m",
                "geom_score",
                "ndvi_amp",
                "ndwi_p50_center",
                "ring_contrast",
                "texture_score",
                "pixel_size_m",
                "source_model",
            ]
        )
    fmt = _write_candidates(df, out_parquet=out_parquet, out_csv=out_csv, log=log)

    summary = {
        "generated_at": utc_now_iso(),
        "year": int(args.year),
        "input_dir": str(in_dir.resolve()),
        "tiles_scanned": len(tif_list),
        "tiles_processed": processed,
        "tiles_failed": failed,
        "candidate_rows": int(len(df)),
        "candidates_format": fmt,
        "manifest": str(manifest_path.resolve()),
        "status_counts": tile_status_counts(manifest["tiles"]),
    }
    save_json(out_dir / "feature_summary.json", summary)
    log(f"Finished candidates generation. rows={len(df)} processed={processed} failed={failed}")
    return 0


def build_parser(subparsers) -> None:
    p = subparsers.add_parser("generate-candidates", help="Generate fast circle candidates from Landsat composites")
    p.add_argument("--year", type=int, required=True, help="Year for output labeling")
    p.add_argument("--input-dir", required=True, help="Directory containing yearly composite GeoTIFFs")
    p.add_argument("--out-dir", default="", help="Output directory (default: runs/features/{year})")
    p.add_argument("--manifest", default="", help="Manifest JSON path")
    p.add_argument("--resume", action="store_true", help="Skip completed tiles based on manifest+signature")
    p.add_argument("--min-radius-m", type=float, default=150.0, help="Minimum pivot radius (meters)")
    p.add_argument("--max-radius-m", type=float, default=2500.0, help="Maximum pivot radius (meters)")
    p.add_argument("--hough-dp", type=float, default=1.2, help="HoughCircles dp")
    p.add_argument("--min-dist-px", type=float, default=20.0, help="Minimum distance between circle centers")
    p.add_argument("--hough-param1", type=float, default=100.0, help="HoughCircles Canny high threshold")
    p.add_argument("--hough-param2", type=float, default=18.0, help="HoughCircles accumulator threshold")
    p.add_argument("--canny-low", type=float, default=50.0, help="Canny low threshold")
    p.add_argument("--canny-high", type=float, default=150.0, help="Canny high threshold")
    p.add_argument("--nms-iou", type=float, default=0.35, help="Circle NMS IoU threshold")
    p.add_argument("--max-candidates-per-tile", type=int, default=300, help="Cap kept candidates per tile")
    p.add_argument("--max-raw-circles", type=int, default=3000, help="Cap raw circles evaluated before feature scoring")
    p.add_argument("--region-mask", default="", help="Optional GeoJSON region mask; drop candidates outside mask")
    p.add_argument("--exclude-water", action="store_true", help="Drop candidates with NDWI >= threshold")
    p.add_argument("--water-ndwi-threshold", type=float, default=0.0, help="Water exclusion threshold on NDWI center value")
    p.add_argument("--max-tiles", type=int, default=0, help="Limit number of tiles for smoke runs")
    p.add_argument("--stale-lock-seconds", type=int, default=7200, help="Lock recovery timeout")
    p.add_argument("--force-lock", action="store_true", help="Force lock takeover")
    p.add_argument("--log-file", default="", help="Optional log file path")
    p.set_defaults(func=run_generate_candidates)
