"""Select an explicit validation tile list from the current 2015 raw tile cache."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
from osgeo import gdal
from shapely.geometry import box


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cpis.common.file_utils import ensure_dir, save_json  # noqa: E402
from cpis.common.logging_utils import build_logger  # noqa: E402


gdal.UseExceptions()


CHUNK_SUFFIX_RE = re.compile(r"^(?P<base>.+)-\d{10}-\d{10}$")


@dataclass
class Candidate:
    tile: str
    score: float
    tier: str
    centroid_x: float
    centroid_y: float
    region_bin: str


def _raster_bounds(tif_path: Path):
    ds = gdal.Open(str(tif_path))
    if ds is None:
        raise RuntimeError(f"Could not open raster: {tif_path}")
    gt = ds.GetGeoTransform()
    width = int(ds.RasterXSize)
    height = int(ds.RasterYSize)
    corners = []
    for px, py in ((0, 0), (width, 0), (width, height), (0, height)):
        mx = gt[0] + (px * gt[1]) + (py * gt[2])
        my = gt[3] + (px * gt[4]) + (py * gt[5])
        corners.append((mx, my))
    minx = min(x for x, _ in corners)
    maxx = max(x for x, _ in corners)
    miny = min(y for _, y in corners)
    maxy = max(y for _, y in corners)
    return box(minx, miny, maxx, maxy)


def _source_name_for_path(path_like: str | Path) -> str:
    stem = Path(path_like).stem
    match = CHUNK_SUFFIX_RE.match(stem)
    if match:
        return str(match.group("base"))
    return str(stem)


def _safe_quantile_edges(values: np.ndarray, n_bins: int) -> np.ndarray:
    if values.size == 0:
        return np.array([0.0, 1.0], dtype=float)
    n_bins = max(1, int(n_bins))
    qs = np.linspace(0.0, 1.0, n_bins + 1)
    edges = np.quantile(values, qs)
    edges = np.unique(edges.astype(float))
    if edges.size == 1:
        edges = np.array([edges[0], edges[0] + 1.0], dtype=float)
    return edges


def _assign_bin(value: float, edges: np.ndarray) -> int:
    if edges.size <= 2:
        return 0
    idx = int(np.searchsorted(edges[1:-1], float(value), side="right"))
    return max(0, min(idx, edges.size - 2))


def _normalize(values: np.ndarray) -> np.ndarray:
    values = values.astype(float, copy=False)
    if values.size == 0:
        return values
    lo = float(np.nanmin(values))
    hi = float(np.nanmax(values))
    if not np.isfinite(lo) or not np.isfinite(hi) or math.isclose(lo, hi):
        return np.zeros_like(values, dtype=float)
    return (values - lo) / (hi - lo)


def _distance_ok(candidate: Candidate, selected: list[Candidate], min_distance_m: float) -> bool:
    if min_distance_m <= 0.0:
        return True
    for prev in selected:
        dx = float(candidate.centroid_x) - float(prev.centroid_x)
        dy = float(candidate.centroid_y) - float(prev.centroid_y)
        if math.hypot(dx, dy) < min_distance_m:
            return False
    return True


def _tier_from_score(score: float, q_low: float, q_high: float) -> str:
    if score <= q_low:
        return "low"
    if score <= q_high:
        return "medium"
    return "high"


def _candidate_key(tile: str, score_map: dict[str, float]) -> tuple[float, str]:
    return (-float(score_map[tile]), str(tile))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--imagery-dir", required=True, help="Directory with 2015 raw GeoTIFFs")
    ap.add_argument("--stable-pivots", required=True, help="Stable pivot polygon layer")
    ap.add_argument("--change-zones", required=True, help="Change-zone polygon layer")
    ap.add_argument("--out-root", required=True, help="Output directory for candidate split artifacts")
    ap.add_argument("--val-fraction", type=float, default=0.25, help="Target validation fraction of positive source tiles")
    ap.add_argument("--min-val-tiles", type=int, default=8, help="Minimum number of validation source tiles")
    ap.add_argument("--max-val-tiles", type=int, default=0, help="Maximum validation source tiles; 0 disables cap")
    ap.add_argument("--equal-area-crs", default="EPSG:6933", help="Equal-area CRS used for stats and spacing")
    ap.add_argument("--lon-bins", type=int, default=4, help="Quantile bins for longitude seeding")
    ap.add_argument("--lat-bins", type=int, default=3, help="Quantile bins for latitude seeding")
    ap.add_argument(
        "--min-centroid-distance-km",
        type=float,
        default=250.0,
        help="Preferred minimum centroid spacing between validation tiles during first-pass selection",
    )
    ap.add_argument("--log-file", default="", help="Optional log file")
    args = ap.parse_args()

    imagery_dir = Path(args.imagery_dir)
    if not imagery_dir.exists():
        raise FileNotFoundError(f"Imagery dir not found: {imagery_dir}")

    out_root = ensure_dir(args.out_root)
    log = build_logger(args.log_file if args.log_file else (out_root / "select_val_tiles.log"))

    tif_paths = sorted(p for p in imagery_dir.glob("*.tif") if p.is_file())
    if not tif_paths:
        raise RuntimeError(f"No GeoTIFFs found in {imagery_dir}")

    stable = gpd.read_file(args.stable_pivots)
    change = gpd.read_file(args.change_zones)
    if stable.empty:
        raise RuntimeError(f"Stable pivot layer is empty: {args.stable_pivots}")
    if stable.crs is None:
        raise RuntimeError(f"Stable pivot layer missing CRS: {args.stable_pivots}")
    if change.empty:
        raise RuntimeError(f"Change-zone layer is empty: {args.change_zones}")
    if change.crs is None:
        raise RuntimeError(f"Change-zone layer missing CRS: {args.change_zones}")

    rows = [{"tile": _source_name_for_path(tif_path), "geometry": _raster_bounds(tif_path)} for tif_path in tif_paths]
    tiles_wgs = gpd.GeoDataFrame(rows, crs="EPSG:4326").dissolve(by="tile", as_index=False)
    tiles_eq = tiles_wgs.to_crs(args.equal_area_crs)
    stable_eq = stable.to_crs(args.equal_area_crs).reset_index(drop=True)
    change_eq = change.to_crs(args.equal_area_crs).reset_index(drop=True)

    stable_eq["stable_src_id"] = np.arange(len(stable_eq), dtype=int)
    stable_eq["stable_area_m2"] = stable_eq.geometry.area.astype(float)
    change_eq["change_src_id"] = np.arange(len(change_eq), dtype=int)

    stable_join = gpd.sjoin(
        tiles_eq[["tile", "geometry"]],
        stable_eq[["stable_src_id", "stable_area_m2", "geometry"]],
        how="left",
        predicate="intersects",
    )
    change_join = gpd.sjoin(
        tiles_eq[["tile", "geometry"]],
        change_eq[["change_src_id", "geometry"]],
        how="left",
        predicate="intersects",
    )

    stable_count_map = (
        stable_join.groupby("tile")["stable_src_id"].apply(lambda s: int(s.notna().sum())).to_dict()
    )
    stable_area_map = (
        stable_join.groupby("tile")["stable_area_m2"].apply(lambda s: float(s.dropna().sum())).to_dict()
    )
    stable_ids_map = (
        stable_join.groupby("tile")["stable_src_id"].apply(lambda s: [int(v) for v in s.dropna().tolist()]).to_dict()
    )
    change_count_map = (
        change_join.groupby("tile")["change_src_id"].apply(lambda s: int(s.notna().sum())).to_dict()
    )

    boundary_touch_map: dict[str, int] = {}
    for _, tile_row in tiles_eq.iterrows():
        tile = str(tile_row["tile"])
        stable_ids = stable_ids_map.get(tile, [])
        if not stable_ids:
            boundary_touch_map[tile] = 0
            continue
        boundary = tile_row.geometry.boundary
        touches = 0
        for sid in stable_ids:
            geom = stable_eq.iloc[int(sid)].geometry
            if geom.is_empty:
                continue
            if boundary.intersects(geom):
                touches += 1
        boundary_touch_map[tile] = int(touches)

    tiles_wgs["stable_count"] = tiles_wgs["tile"].map(lambda k: int(stable_count_map.get(k, 0)))
    tiles_wgs["stable_area_m2"] = tiles_wgs["tile"].map(lambda k: float(stable_area_map.get(k, 0.0)))
    tiles_wgs["change_count"] = tiles_wgs["tile"].map(lambda k: int(change_count_map.get(k, 0)))
    tiles_wgs["boundary_touch_count"] = tiles_wgs["tile"].map(lambda k: int(boundary_touch_map.get(k, 0)))

    positive_mask = tiles_wgs["stable_count"].to_numpy(dtype=int) > 0
    n_positive = int(np.sum(positive_mask))
    if n_positive <= 1:
        raise RuntimeError(f"Need at least 2 positive source tiles to build a validation list; found {n_positive}")

    target_val = int(round(n_positive * float(args.val_fraction)))
    target_val = max(int(args.min_val_tiles), target_val)
    target_val = min(target_val, n_positive - 1)
    if int(args.max_val_tiles) > 0:
        target_val = min(target_val, int(args.max_val_tiles))

    pos_idx = np.where(positive_mask)[0]
    pos_log_stable = np.log1p(tiles_wgs.iloc[pos_idx]["stable_count"].to_numpy(dtype=float))
    pos_log_change = np.log1p(tiles_wgs.iloc[pos_idx]["change_count"].to_numpy(dtype=float))
    pos_log_boundary = np.log1p(tiles_wgs.iloc[pos_idx]["boundary_touch_count"].to_numpy(dtype=float))
    score_pos = (
        (0.45 * _normalize(pos_log_stable))
        + (0.35 * _normalize(pos_log_change))
        + (0.20 * _normalize(pos_log_boundary))
    )
    tiles_wgs["difficulty_score"] = 0.0
    tiles_wgs.loc[pos_idx, "difficulty_score"] = score_pos

    q_low, q_high = np.quantile(score_pos, [1 / 3, 2 / 3])
    tiles_wgs["difficulty_tier"] = "none"
    for idx in pos_idx:
        score = float(tiles_wgs.iloc[idx]["difficulty_score"])
        tiles_wgs.at[idx, "difficulty_tier"] = _tier_from_score(score, float(q_low), float(q_high))

    positive_tiles = tiles_wgs.loc[positive_mask].copy()
    bounds = positive_tiles.geometry.bounds
    positive_tiles["centroid_lon"] = ((bounds["minx"] + bounds["maxx"]) / 2.0).astype(float)
    positive_tiles["centroid_lat"] = ((bounds["miny"] + bounds["maxy"]) / 2.0).astype(float)
    lon_edges = _safe_quantile_edges(positive_tiles["centroid_lon"].to_numpy(dtype=float), int(args.lon_bins))
    lat_edges = _safe_quantile_edges(positive_tiles["centroid_lat"].to_numpy(dtype=float), int(args.lat_bins))
    positive_tiles["lon_bin"] = positive_tiles["centroid_lon"].apply(lambda v: _assign_bin(float(v), lon_edges))
    positive_tiles["lat_bin"] = positive_tiles["centroid_lat"].apply(lambda v: _assign_bin(float(v), lat_edges))
    positive_tiles["region_bin"] = positive_tiles.apply(
        lambda row: f"lat{int(row['lat_bin'])}_lon{int(row['lon_bin'])}", axis=1
    )

    positive_eq = tiles_eq.merge(
        positive_tiles[
            [
                "tile",
                "stable_count",
                "stable_area_m2",
                "change_count",
                "boundary_touch_count",
                "difficulty_score",
                "difficulty_tier",
                "region_bin",
                "centroid_lon",
                "centroid_lat",
            ]
        ],
        on="tile",
        how="inner",
    )
    positive_eq["centroid_x"] = positive_eq.geometry.centroid.x.astype(float)
    positive_eq["centroid_y"] = positive_eq.geometry.centroid.y.astype(float)
    positive_eq = positive_eq.sort_values(["difficulty_score", "stable_count", "change_count"], ascending=False)

    score_map = {str(row.tile): float(row.difficulty_score) for _, row in positive_eq.iterrows()}
    record_map = {
        str(row.tile): Candidate(
            tile=str(row.tile),
            score=float(row.difficulty_score),
            tier=str(row.difficulty_tier),
            centroid_x=float(row.centroid_x),
            centroid_y=float(row.centroid_y),
            region_bin=str(row.region_bin),
        )
        for _, row in positive_eq.iterrows()
    }

    selected: list[Candidate] = []
    selected_names: set[str] = set()
    min_distance_m = float(args.min_centroid_distance_km) * 1000.0

    # Seed the validation set with one positive tile per occupied geographic bin where possible.
    bin_to_tiles: dict[str, list[str]] = {}
    for _, row in positive_eq.iterrows():
        bin_to_tiles.setdefault(str(row.region_bin), []).append(str(row.tile))
    ordered_bins = sorted(
        bin_to_tiles,
        key=lambda b: _candidate_key(bin_to_tiles[b][0], score_map),
    )

    for region_bin in ordered_bins:
        if len(selected) >= target_val:
            break
        for tile in sorted(bin_to_tiles[region_bin], key=lambda t: _candidate_key(t, score_map)):
            cand = record_map[tile]
            if tile in selected_names:
                continue
            if _distance_ok(cand, selected, min_distance_m):
                selected.append(cand)
                selected_names.add(tile)
                break

    # Fill remaining slots with a mix of difficulty tiers.
    tier_order = ["high", "medium", "low"]
    remaining_by_tier = {
        tier: [
            record_map[str(row.tile)]
            for _, row in positive_eq[positive_eq["difficulty_tier"] == tier].iterrows()
            if str(row.tile) not in selected_names
        ]
        for tier in tier_order
    }

    def _fill(pass_distance: bool) -> None:
        made_progress = True
        while len(selected) < target_val and made_progress:
            made_progress = False
            for tier in tier_order:
                candidates = remaining_by_tier[tier]
                while candidates:
                    cand = candidates.pop(0)
                    if cand.tile in selected_names:
                        continue
                    if pass_distance and not _distance_ok(cand, selected, min_distance_m):
                        continue
                    selected.append(cand)
                    selected_names.add(cand.tile)
                    made_progress = True
                    break
                if len(selected) >= target_val:
                    break

    _fill(pass_distance=True)
    if len(selected) < target_val:
        # Rebuild remaining pools and relax the spacing constraint to hit the target count.
        remaining_by_tier = {
            tier: sorted(
                [record_map[str(row.tile)] for _, row in positive_eq[positive_eq["difficulty_tier"] == tier].iterrows()
                 if str(row.tile) not in selected_names],
                key=lambda c: (-c.score, c.tile),
            )
            for tier in tier_order
        }
        _fill(pass_distance=False)

    val_tiles = sorted(c.tile for c in selected)
    meta_cols = positive_tiles.set_index("tile")[
        ["difficulty_score", "difficulty_tier", "region_bin", "centroid_lon", "centroid_lat"]
    ]
    for col in meta_cols.columns:
        tiles_wgs[col] = tiles_wgs["tile"].map(meta_cols[col].to_dict())
    tiles_wgs["selected_val"] = tiles_wgs["tile"].isin(val_tiles)

    val_list_path = out_root / "val_tiles.txt"
    val_list_path.write_text("\n".join(val_tiles) + ("\n" if val_tiles else ""), encoding="utf-8")

    csv_path = out_root / "tile_stats.csv"
    fieldnames = [
        "tile",
        "stable_count",
        "stable_area_m2",
        "change_count",
        "boundary_touch_count",
        "difficulty_score",
        "difficulty_tier",
        "region_bin",
        "centroid_lon",
        "centroid_lat",
        "selected_val",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for _, row in tiles_wgs.sort_values(["selected_val", "difficulty_score", "stable_count"], ascending=[False, False, False]).iterrows():
            writer.writerow(
                {
                    "tile": row["tile"],
                    "stable_count": int(row["stable_count"]),
                    "stable_area_m2": float(row["stable_area_m2"]),
                    "change_count": int(row["change_count"]),
                    "boundary_touch_count": int(row["boundary_touch_count"]),
                    "difficulty_score": float(row.get("difficulty_score") or 0.0),
                    "difficulty_tier": row.get("difficulty_tier") or "none",
                    "region_bin": row.get("region_bin") or "",
                    "centroid_lon": float(row.get("centroid_lon") or 0.0),
                    "centroid_lat": float(row.get("centroid_lat") or 0.0),
                    "selected_val": bool(row["selected_val"]),
                }
            )

    tile_stats_gpkg = out_root / "tile_stats.gpkg"
    tiles_wgs.to_file(tile_stats_gpkg, driver="GPKG")
    selected_gpkg = out_root / "selected_val_tiles.gpkg"
    tiles_wgs[tiles_wgs["selected_val"]].copy().to_file(selected_gpkg, driver="GPKG")

    tier_counts: dict[str, int] = {}
    region_counts: dict[str, int] = {}
    for cand in selected:
        tier_counts[cand.tier] = tier_counts.get(cand.tier, 0) + 1
        region_counts[cand.region_bin] = region_counts.get(cand.region_bin, 0) + 1

    summary = {
        "imagery_dir": str(imagery_dir.resolve()),
        "stable_pivots": str(Path(args.stable_pivots).resolve()),
        "change_zones": str(Path(args.change_zones).resolve()),
        "out_root": str(out_root.resolve()),
        "raw_tile_count": int(len(tif_paths)),
        "positive_tile_count": int(n_positive),
        "target_val_tiles": int(target_val),
        "selected_val_tiles": int(len(val_tiles)),
        "val_fraction": float(args.val_fraction),
        "min_val_tiles": int(args.min_val_tiles),
        "max_val_tiles": int(args.max_val_tiles),
        "min_centroid_distance_km": float(args.min_centroid_distance_km),
        "lon_bins": int(args.lon_bins),
        "lat_bins": int(args.lat_bins),
        "score_formula": {
            "stable_count_log1p_norm": 0.45,
            "change_count_log1p_norm": 0.35,
            "boundary_touch_count_log1p_norm": 0.20,
        },
        "selected_tiles": val_tiles,
        "selected_tier_counts": tier_counts,
        "selected_region_counts": region_counts,
        "outputs": {
            "val_tiles": str(val_list_path.resolve()),
            "tile_stats_csv": str(csv_path.resolve()),
            "tile_stats_gpkg": str(tile_stats_gpkg.resolve()),
            "selected_val_tiles_gpkg": str(selected_gpkg.resolve()),
        },
    }
    save_json(out_root / "selection_summary.json", summary)

    log(
        f"Selected {len(val_tiles)} validation tiles from {n_positive} positive tiles "
        f"(raw_tiles={len(tif_paths)} target_val={target_val})"
    )
    log(f"Wrote validation tile list: {val_list_path}")
    log(f"Wrote tile stats CSV: {csv_path}")
    log(f"Wrote tile stats GPKG: {tile_stats_gpkg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
