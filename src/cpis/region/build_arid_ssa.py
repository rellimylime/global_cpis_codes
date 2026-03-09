"""Build canonical arid-SSA region mask."""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

from cpis.common.config import load_yaml
from cpis.common.constants import DEFAULT_REGION_GEOJSON, DEFAULT_REGION_SUMMARY, DEFAULT_SSA_COUNTRIES_CONFIG
from cpis.common.file_utils import ensure_dir, save_json
from cpis.common.logging_utils import build_logger
from cpis.common.time_utils import utc_now_iso


def _norm_country_name(name: str) -> str:
    x = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    x = x.strip().lower()
    x = re.sub(r"[^a-z0-9]+", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    if x.startswith("the "):
        x = x[4:]
    aliases = {
        "dem rep congo": "democratic republic of the congo",
        "dr congo": "democratic republic of the congo",
        "drc": "democratic republic of the congo",
        "republic of congo": "congo",
        "congo brazzaville": "congo",
        "congo kinshasa": "democratic republic of the congo",
        "ivory coast": "cote d ivoire",
        "gambia": "gambia",
        "south sudan": "south sudan",
        "s sudan": "south sudan",
        "swaziland": "eswatini",
        "cape verde": "cabo verde",
        "tanzania": "united republic of tanzania",
    }
    return aliases.get(x, x)


def _resolve_default_arid_shp() -> Path:
    candidates = [
        Path("SSA_Arid_by_Country-shp") / "SSA_Arid_by_Country.shp",
        Path("Africa_Arid_Regions_All-shp") / "Africa_Arid_Regions_All-shp.shp",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Fallback to the legacy location if neither exists.
    return Path("Africa_Arid_Regions_All-shp") / "Africa_Arid_Regions_All-shp.shp"


def _load_ssa_boundaries(path: Path | None, log) -> gpd.GeoDataFrame:
    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"SSA boundaries file not found: {path}")
        gdf = gpd.read_file(path)
        log(f"Loaded SSA boundaries from {path} ({len(gdf)} rows)")
        return gdf

    # Fallback 1: geodatasets package (if installed).
    try:
        import geodatasets

        ds_path = geodatasets.get_path("naturalearth.countries")
        gdf = gpd.read_file(ds_path)
        log(f"Loaded fallback boundaries via geodatasets: {ds_path}")
        return gdf
    except Exception:
        pass

    # Fallback 2: direct Natural Earth hosted ZIP.
    ne_url = "https://naturalearth.s3.amazonaws.com/110m_cultural/ne_110m_admin_0_countries.zip"
    try:
        gdf = gpd.read_file(ne_url)
        log(f"Loaded fallback boundaries from Natural Earth URL: {ne_url}")
        return gdf
    except Exception as exc:
        raise RuntimeError(
            "No --ssa-boundary path provided and fallback boundary sources failed. "
            "Provide --ssa-boundary explicitly."
        ) from exc


def _to_epsg4326(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        return gdf.set_crs("EPSG:4326")
    if str(gdf.crs).upper() != "EPSG:4326":
        return gdf.to_crs("EPSG:4326")
    return gdf


def _pick_country_field(gdf: gpd.GeoDataFrame, preferred: str | None) -> str:
    if preferred and preferred in gdf.columns:
        return preferred

    candidates = [
        "name",
        "NAME",
        "NAME_EN",
        "ADMIN",
        "SOVEREIGNT",
        "country",
        "COUNTRY",
        "adm0_name",
        "ADM0_NAME",
    ]
    for c in candidates:
        if c in gdf.columns:
            return c
    raise RuntimeError(
        "Could not infer country field from SSA boundary file. "
        "Pass --country-field with an existing column name."
    )


def _validate_geometry(geom: BaseGeometry) -> None:
    if geom is None or geom.is_empty:
        raise RuntimeError("Resulting arid SSA geometry is empty.")
    if not geom.is_valid:
        geom = geom.buffer(0)
        if geom.is_empty or not geom.is_valid:
            raise RuntimeError("Resulting arid SSA geometry is invalid and could not be repaired.")
    minx, miny, maxx, maxy = geom.bounds
    if not (-30.0 <= minx <= 60.0 and -40.0 <= miny <= 40.0 and -10.0 <= maxx <= 65.0 and 0.0 <= maxy <= 45.0):
        raise RuntimeError(f"Resulting bounds look suspicious for Africa: {(minx, miny, maxx, maxy)}")


def run_build_arid_ssa(args: argparse.Namespace) -> int:
    log = build_logger(args.log_file)
    arid_path = Path(args.arid_shp) if args.arid_shp else _resolve_default_arid_shp()
    out_geojson = Path(args.out_geojson) if args.out_geojson else DEFAULT_REGION_GEOJSON
    out_summary = Path(args.out_summary) if args.out_summary else DEFAULT_REGION_SUMMARY
    cfg_path = Path(args.ssa_config) if args.ssa_config else DEFAULT_SSA_COUNTRIES_CONFIG

    if not arid_path.exists():
        raise FileNotFoundError(f"Arid shapefile not found: {arid_path}")

    arid = _to_epsg4326(gpd.read_file(arid_path))
    log(f"Loaded arid polygons: {len(arid)} rows")

    arid_union = arid.geometry.union_all() if hasattr(arid.geometry, "union_all") else arid.unary_union

    if args.arid_is_ssa:
        arid_ssa = arid_union
        country_field = args.country_field if args.country_field else "NAME"
        missing = []
        matched_rows = int(len(arid))
        ssa_count = None
        ssa_boundary_desc = "not_used_arid_is_ssa=true"
        log("Using arid shapefile as authoritative arid-SSA mask (--arid-is-ssa).")
    else:
        cfg = load_yaml(cfg_path)
        ssa_countries = cfg.get("ssa_countries", [])
        if not isinstance(ssa_countries, list) or not ssa_countries:
            raise RuntimeError(f"'ssa_countries' must be a non-empty list in {cfg_path}")
        ssa_norm = {_norm_country_name(str(x)) for x in ssa_countries}
        ssa_count = len(ssa_norm)
        log(f"Loaded SSA config with {ssa_count} countries from {cfg_path}")

        ssa_boundaries = _to_epsg4326(_load_ssa_boundaries(Path(args.ssa_boundary) if args.ssa_boundary else None, log))
        country_field = _pick_country_field(ssa_boundaries, args.country_field)
        log(f"Using country field: {country_field}")

        ssa_boundaries["_country_norm"] = ssa_boundaries[country_field].astype(str).map(_norm_country_name)
        in_ssa = ssa_boundaries[ssa_boundaries["_country_norm"].isin(ssa_norm)].copy()
        missing = sorted(ssa_norm - set(in_ssa["_country_norm"].unique()))
        matched_rows = int(len(in_ssa))
        ssa_boundary_desc = (
            str(Path(args.ssa_boundary).resolve()) if args.ssa_boundary else "geopandas:naturalearth_lowres"
        )
        log(f"SSA boundaries matched: {len(in_ssa)} rows; missing countries in boundary source: {len(missing)}")

        if in_ssa.empty:
            raise RuntimeError("No SSA country polygons matched. Check --country-field and config names.")
        ssa_union = in_ssa.geometry.union_all() if hasattr(in_ssa.geometry, "union_all") else in_ssa.unary_union
        arid_ssa = arid_union.intersection(ssa_union)

    _validate_geometry(arid_ssa)

    out_gdf = gpd.GeoDataFrame(
        [{"region": "arid_ssa", "source": "arid_intersection"}],
        geometry=[arid_ssa],
        crs="EPSG:4326",
    )
    ensure_dir(out_geojson.parent)
    ensure_dir(out_summary.parent)
    out_gdf.to_file(out_geojson, driver="GeoJSON")
    log(f"Wrote region mask: {out_geojson}")

    minx, miny, maxx, maxy = [float(v) for v in arid_ssa.bounds]
    summary: dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "arid_shp": str(arid_path.resolve()),
        "arid_is_ssa": bool(args.arid_is_ssa),
        "ssa_boundary": ssa_boundary_desc,
        "ssa_config": str(cfg_path.resolve()) if not args.arid_is_ssa else "not_used_arid_is_ssa=true",
        "country_field": country_field,
        "ssa_countries_count": ssa_count,
        "matched_boundary_rows": matched_rows,
        "missing_country_count": len(missing),
        "missing_countries": missing,
        "bounds": [minx, miny, maxx, maxy],
        "geom_type": arid_ssa.geom_type,
        "valid": bool(arid_ssa.is_valid),
        "empty": bool(arid_ssa.is_empty),
    }
    save_json(out_summary, summary)
    log(f"Wrote summary: {out_summary}")
    return 0


def build_parser(subparsers) -> None:
    p = subparsers.add_parser(
        "build-arid-ssa",
        help="Build canonical arid SSA region by intersecting arid polygons with SSA countries",
    )
    p.add_argument("--arid-shp", default="", help="Arid polygon shapefile path")
    p.add_argument("--arid-is-ssa", action="store_true", help="Treat arid shapefile as authoritative arid-SSA mask")
    p.add_argument("--ssa-boundary", default="", help="Country boundary file path")
    p.add_argument("--country-field", default="", help="Country name field in boundary file")
    p.add_argument("--ssa-config", default=str(DEFAULT_SSA_COUNTRIES_CONFIG), help="SSA countries config YAML")
    p.add_argument("--out-geojson", default=str(DEFAULT_REGION_GEOJSON), help="Output GeoJSON path")
    p.add_argument("--out-summary", default=str(DEFAULT_REGION_SUMMARY), help="Output summary JSON path")
    p.add_argument("--log-file", default="", help="Optional log file path")
    p.set_defaults(func=run_build_arid_ssa)
