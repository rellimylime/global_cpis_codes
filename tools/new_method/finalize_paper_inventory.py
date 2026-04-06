"""Normalize a reviewed CPI layer into the 2015 inventory delivery schema."""

from __future__ import annotations

import argparse
import math
import sys
import uuid
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cpis.common.constants import DEFAULT_EQUAL_AREA_CRS  # noqa: E402
from cpis.common.file_utils import ensure_dir, save_json  # noqa: E402
from cpis.common.logging_utils import build_logger  # noqa: E402


def _det_id(year: int, idx: int) -> str:
    return f"{year}_{idx:07d}_{uuid.uuid4().hex[:8]}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="Reviewed polygon/point layer")
    ap.add_argument("--out", required=True, help="Output vector path (.gpkg or .shp)")
    ap.add_argument("--year", type=int, default=2015, help="Inventory year")
    ap.add_argument("--equal-area-crs", default=DEFAULT_EQUAL_AREA_CRS, help="Equal-area CRS for metric calculations")
    ap.add_argument("--confidence-field", default="", help="Optional field to map into confidence")
    ap.add_argument("--country-field", default="NAME", help="Optional field to map into country")
    ap.add_argument("--geometry-status-field", default="", help="Optional field with geometry status")
    ap.add_argument("--qa-status", default="reviewed", help="QA status to stamp on every output row")
    ap.add_argument("--source-imagery", default="landsat_full_year_2015_rgbnir", help="Source imagery label")
    ap.add_argument("--model-version", default="rse2023_2015_v1", help="Model/version label")
    ap.add_argument("--log-file", default="", help="Optional log file")
    args = ap.parse_args()

    out_path = Path(args.out)
    log = build_logger(args.log_file if args.log_file else (out_path.parent / "finalize_paper_inventory.log"))
    gdf = gpd.read_file(args.input)
    if gdf.empty:
        raise RuntimeError(f"Input layer is empty: {args.input}")
    if gdf.crs is None:
        raise RuntimeError(f"Input layer missing CRS: {args.input}")

    work = gdf.copy()
    work = work[work.geometry.notna()].copy()
    work = work[~work.geometry.is_empty].copy()
    if work.empty:
        raise RuntimeError("No valid geometries remain after dropping empty rows.")

    eq = work.to_crs(args.equal_area_crs)
    geom_types = eq.geometry.geom_type.fillna("")
    is_point = geom_types.isin(["Point", "MultiPoint"])
    centroids_eq = eq.geometry.centroid
    centroids_wgs = gpd.GeoSeries(centroids_eq, crs=args.equal_area_crs).to_crs("EPSG:4326")

    area_m2_eq = np.where(is_point.values, 0.0, eq.geometry.area.astype(float).values)
    radius_m_eq = np.sqrt(np.clip(area_m2_eq, 0.0, None) / math.pi)

    out_gdf = work.to_crs("EPSG:4326").copy()
    out_gdf["det_id"] = [_det_id(int(args.year), i + 1) for i in range(len(out_gdf))]
    out_gdf["year"] = int(args.year)
    out_gdf["confidence"] = (
        pd.to_numeric(out_gdf[args.confidence_field], errors="coerce")
        if args.confidence_field and args.confidence_field in out_gdf.columns
        else np.nan
    )
    out_gdf["qa_status"] = str(args.qa_status)
    if args.geometry_status_field and args.geometry_status_field in out_gdf.columns:
        out_gdf["geometry_status"] = out_gdf[args.geometry_status_field].astype(str)
    else:
        out_gdf["geometry_status"] = np.where(is_point.values, "point_fallback", "polygon")
    if args.country_field and args.country_field in out_gdf.columns:
        out_gdf["country"] = out_gdf[args.country_field].astype(str)
    else:
        out_gdf["country"] = "unknown"
    out_gdf["center_lon"] = centroids_wgs.x.astype(float).values
    out_gdf["center_lat"] = centroids_wgs.y.astype(float).values
    out_gdf["area_m2_eq"] = area_m2_eq.astype(float)
    out_gdf["radius_m_eq"] = radius_m_eq.astype(float)
    out_gdf["source_imagery"] = str(args.source_imagery)
    out_gdf["model_version"] = str(args.model_version)

    final_cols = [
        "det_id",
        "year",
        "country",
        "confidence",
        "qa_status",
        "geometry_status",
        "center_lon",
        "center_lat",
        "area_m2_eq",
        "radius_m_eq",
        "source_imagery",
        "model_version",
        "geometry",
    ]
    final_gdf = out_gdf[final_cols].copy()

    ensure_dir(out_path.parent)
    if out_path.suffix.lower() == ".gpkg":
        final_gdf.to_file(out_path, driver="GPKG")
    else:
        final_gdf.to_file(out_path)
    summary = {
        "input": str(Path(args.input).resolve()),
        "output": str(out_path.resolve()),
        "year": int(args.year),
        "equal_area_crs": str(args.equal_area_crs),
        "rows": int(len(final_gdf)),
        "polygon_rows": int((final_gdf["geometry_status"] == "polygon").sum()),
        "point_rows": int((final_gdf["geometry_status"] == "point_fallback").sum()),
        "source_imagery": str(args.source_imagery),
        "model_version": str(args.model_version),
    }
    save_json(out_path.with_suffix(".summary.json"), summary)
    log(f"Wrote final inventory: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
