"""Export a QGIS-ready false-negative layer after active-label inference.

For each inferred tile:
  1. Loads the model's output raster mask (union_segm_<score_thr>.tif)
  2. Loads anchor-truth stable pivots that fall on that tile
  3. Marks each anchor pivot as FOUND or MISSED based on whether the mask
     has any non-zero pixels within the pivot polygon (+ a small buffer)
  4. Exports two GeoPackage layers:
       - missed_pivots.gpkg   : anchor truth pivots the model didn't detect
                                → these are your labeling targets
       - found_pivots.gpkg    : anchor truth pivots the model DID detect
                                → skip these in QGIS
  5. Also exports model_predictions.gpkg : all predicted polygons as vectors
                                → overlay to see what the model found

Load all three in QGIS on top of the raw raster for a complete picture.

Usage
-----
python tools/new_method/export_fn_layer.py \
    --inference-dir runs/new_method/rse2023_2015_v1/active_label_v1/inference \
    --anchor-truth  runs/new_method/rse2023_2015_v1/anchor_truth/overlays/stable_pivots.gpkg \
    --out-dir       runs/new_method/rse2023_2015_v1/active_label_v1/qgis_layers \
    --score-thr 0.3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes as rasterio_shapes
from shapely.geometry import shape as shapely_shape, box as shapely_box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = str(ROOT / "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from cpis.common.file_utils import ensure_dir
from cpis.common.logging_utils import build_logger


def _load_mask_polygons(mask_tif: Path, min_area_m2: float = 5000.0) -> gpd.GeoDataFrame:
    """Vectorise a binary GeoTIFF mask → GeoDataFrame of polygons in EPSG:4326."""
    with rasterio.open(mask_tif) as src:
        data = src.read(1)
        transform = src.transform
        crs = src.crs
        binary = (data > 0).astype(np.uint8)
        geoms = []
        for geom_dict, val in rasterio_shapes(binary, transform=transform):
            if val == 1:
                g = shapely_shape(geom_dict)
                if g.is_valid and not g.is_empty:
                    geoms.append(g)
        if not geoms:
            return gpd.GeoDataFrame(geometry=[], crs=crs)
        gdf = gpd.GeoDataFrame(geometry=geoms, crs=crs)
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    # Filter tiny slivers
    gdf["area_m2"] = gdf.to_crs("EPSG:3857").geometry.area
    gdf = gdf[gdf["area_m2"] >= min_area_m2].copy()
    gdf = gdf.reset_index(drop=True)
    return gdf


def _tile_bbox(mask_tif: Path) -> "shapely.geometry.Polygon":
    """Return the bounding box of a raster in EPSG:4326."""
    with rasterio.open(mask_tif) as src:
        bounds = src.bounds
        crs = src.crs
    bbox = shapely_box(bounds.left, bounds.bottom, bounds.right, bounds.top)
    if crs.to_epsg() != 4326:
        import pyproj
        from shapely.ops import transform as shp_transform
        proj = pyproj.Transformer.from_crs(crs.to_epsg(), 4326, always_xy=True)
        bbox = shp_transform(proj.transform, bbox)
    return bbox


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inference-dir", required=True,
                    help="run_paper_inference.py out-root (contains segmentation_masks/)")
    ap.add_argument("--anchor-truth", required=True,
                    help="stable_pivots.gpkg from anchor_truth/overlays/")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--score-thr", type=float, default=0.3,
                    help="Score threshold used during inference (selects which mask file to load)")
    ap.add_argument("--buffer-m", type=float, default=150.0,
                    help="Buffer around each anchor pivot (metres) when checking for mask overlap")
    ap.add_argument("--min-iou", type=float, default=0.05,
                    help="Minimum overlap fraction to count as 'found'")
    args = ap.parse_args()

    out_dir = ensure_dir(Path(args.out_dir))
    log = build_logger(out_dir / "export_fn_layer.log")

    infer_dir = Path(args.inference_dir)
    seg_dir = infer_dir / "segmentation_masks"
    if not seg_dir.exists():
        log(f"ERROR: segmentation_masks not found at {seg_dir}")
        return 1

    anchor = gpd.read_file(args.anchor_truth)
    if anchor.crs.to_epsg() != 4326:
        anchor = anchor.to_crs("EPSG:4326")
    log(f"Loaded anchor truth: {len(anchor)} pivots")

    # Buffer size in degrees (approx): 150m ≈ 0.00135 deg at equator
    buffer_deg = args.buffer_m / 111_000.0

    all_missed = []
    all_found = []
    all_predictions = []

    # Each tile has its own subdirectory under segmentation_masks/
    tile_dirs = sorted(d for d in seg_dir.iterdir() if d.is_dir())
    log(f"Found {len(tile_dirs)} tile inference result directories")

    for tile_dir in tile_dirs:
        tile_name = tile_dir.name  # e.g. cpis_landsat_2015_tile_000001.tif
        stem = Path(tile_name).stem  # cpis_landsat_2015_tile_000001

        # Find the mask file for our score threshold
        thr_str = str(args.score_thr)
        mask_candidates = list(tile_dir.glob(f"*union_segm_{thr_str}.tif"))
        if not mask_candidates:
            # Try without trailing zero (0.3 vs 0.30)
            thr_alt = f"{args.score_thr:.1f}"
            mask_candidates = list(tile_dir.glob(f"*union_segm_{thr_alt}.tif"))
        if not mask_candidates:
            log(f"  {stem}: no mask at score_thr={args.score_thr} — skipping")
            continue

        mask_tif = mask_candidates[0]

        # Load tile bounding box to subset anchor truth
        try:
            tile_bbox = _tile_bbox(mask_tif)
        except Exception as e:
            log(f"  {stem}: failed reading bbox — {e}")
            continue

        tile_anchors = anchor[anchor.geometry.intersects(tile_bbox)].copy()
        if tile_anchors.empty:
            log(f"  {stem}: no anchor pivots in tile extent")
            continue

        # Vectorise the prediction mask
        try:
            preds = _load_mask_polygons(mask_tif)
        except Exception as e:
            log(f"  {stem}: failed vectorising mask — {e}")
            continue

        # Tag predictions with tile name
        if not preds.empty:
            preds["tile"] = stem
            all_predictions.append(preds)

        # Build union of all predictions for fast overlap check
        if preds.empty:
            pred_union = None
        else:
            pred_union = unary_union(preds.geometry)

        # For each anchor pivot: check overlap with predictions
        found_ids = []
        missed_ids = []

        for idx, row in tile_anchors.iterrows():
            pivot_geom = row.geometry
            buffered = pivot_geom.buffer(buffer_deg)

            if pred_union is None:
                missed_ids.append(idx)
                continue

            intersection_area = buffered.intersection(pred_union).area
            pivot_area = buffered.area
            overlap_frac = intersection_area / pivot_area if pivot_area > 0 else 0.0

            if overlap_frac >= args.min_iou:
                found_ids.append(idx)
            else:
                missed_ids.append(idx)

        tile_found = tile_anchors.loc[found_ids].copy()
        tile_missed = tile_anchors.loc[missed_ids].copy()
        tile_found["tile"] = stem
        tile_missed["tile"] = stem
        tile_found["status"] = "found"
        tile_missed["status"] = "missed"

        log(f"  {stem}: anchors={len(tile_anchors)}  "
            f"found={len(tile_found)}  missed={len(tile_missed)}  "
            f"predictions={len(preds)}")

        all_found.append(tile_found)
        all_missed.append(tile_missed)

    if not all_missed and not all_found:
        log("No results produced — check that inference ran successfully")
        return 1

    def _concat(frames):
        import pandas as pd
        return gpd.GeoDataFrame(
            pd.concat(frames, ignore_index=True),
            crs="EPSG:4326"
        ) if frames else gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    missed_gdf = _concat(all_missed)
    found_gdf = _concat(all_found)
    preds_gdf = _concat(all_predictions)

    # Save layers
    missed_path = out_dir / "missed_pivots.gpkg"
    found_path = out_dir / "found_pivots.gpkg"
    preds_path = out_dir / "model_predictions.gpkg"

    missed_gdf.to_file(missed_path, driver="GPKG")
    found_gdf.to_file(found_path, driver="GPKG")
    preds_gdf.to_file(preds_path, driver="GPKG")

    total_anchors = len(missed_gdf) + len(found_gdf)
    recall = len(found_gdf) / total_anchors if total_anchors > 0 else 0.0

    log(f"\nSummary across all tiles:")
    log(f"  Total anchor pivots evaluated: {total_anchors}")
    log(f"  Model found (TP):  {len(found_gdf)}  ({recall:.1%})")
    log(f"  Model missed (FN): {len(missed_gdf)}  ({1-recall:.1%})")
    log(f"  Model predictions: {len(preds_gdf)}")
    log(f"\nQGIS layers written to: {out_dir}")
    log(f"  missed_pivots.gpkg    ← YOUR LABELING TARGETS (red dots)")
    log(f"  found_pivots.gpkg     ← already detected, skip these (green)")
    log(f"  model_predictions.gpkg ← model output polygons (blue)")
    log(f"\nIn QGIS:")
    log(f"  1. Load the raw raster(s) from pilot_2015_ssa/raw/")
    log(f"  2. Load missed_pivots.gpkg  — red markers at missed CPI locations")
    log(f"  3. Load model_predictions.gpkg — blue polygons for what was found")
    log(f"  4. For each red marker: zoom in, decide if it's obviously a CPI")
    log(f"     If yes → draw a polygon around it in your new labels layer")
    log(f"     If no  → skip (anchor truth was wrong)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
