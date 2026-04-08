"""Labeling utilities for building training tables."""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from cpis.common.file_utils import ensure_dir, save_json
from cpis.common.geo_utils import circle_polygon_wgs84
from cpis.common.logging_utils import build_logger
from cpis.common.region_filter import RegionMask
from cpis.common.time_utils import utc_now_iso
from cpis.model.train import DEFAULT_FEATURE_COLUMNS

GEO_EXTS = {".gpkg", ".shp", ".geojson"}
EARTH_RADIUS_M = 6_371_008.8


def _load_tabular_or_vector(path: Path, keep_geometry: bool = False) -> pd.DataFrame | gpd.GeoDataFrame:
    ext = path.suffix.lower()
    if ext in GEO_EXTS:
        gdf = gpd.read_file(path)
        if keep_geometry:
            return gdf
        return pd.DataFrame(gdf.drop(columns=["geometry"], errors="ignore"))
    if ext == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _load_candidates(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Candidates table not found: {path}")
    loaded = _load_tabular_or_vector(path, keep_geometry=False)
    if isinstance(loaded, gpd.GeoDataFrame):
        return pd.DataFrame(loaded.drop(columns=["geometry"], errors="ignore"))
    return loaded


def _stratified_sample(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    if n <= 0 or len(df) <= n:
        return df.copy()

    if "geom_score" not in df.columns:
        return df.sample(n=n, random_state=seed).copy()

    work = df.copy()
    try:
        work["_bin"] = pd.qcut(work["geom_score"].rank(method="first"), q=5, duplicates="drop")
    except Exception:
        return df.sample(n=n, random_state=seed).copy()

    groups = []
    per_bin = max(1, n // max(1, work["_bin"].nunique()))
    for _, part in work.groupby("_bin", dropna=False):
        take = min(len(part), per_bin)
        groups.append(part.sample(n=take, random_state=seed))
    out = pd.concat(groups, ignore_index=True)
    if len(out) < n:
        remain = work.drop(index=out.index, errors="ignore")
        if not remain.empty:
            extra = remain.sample(n=min(n - len(out), len(remain)), random_state=seed)
            out = pd.concat([out, extra], ignore_index=True)
    out = out.drop(columns=["_bin"], errors="ignore")
    if len(out) > n:
        out = out.sample(n=n, random_state=seed)
    return out


def _top_confidence_sample(df: pd.DataFrame, n: int) -> pd.DataFrame:
    if n <= 0 or len(df) <= n:
        return df.copy()

    work = df.copy()
    if "geom_score" not in work.columns:
        return work.head(n).copy()

    work["_rank_score"] = pd.to_numeric(work["geom_score"], errors="coerce").fillna(0.0)
    if "ring_contrast" in work.columns:
        work["_rank_score"] += pd.to_numeric(work["ring_contrast"], errors="coerce").fillna(0.0)
    if "texture_score" in work.columns:
        work["_rank_score"] += 0.25 * pd.to_numeric(work["texture_score"], errors="coerce").fillna(0.0)
    work = work.sort_values(["_rank_score", "tile_id"], ascending=[False, True], na_position="last")
    return work.head(n).drop(columns=["_rank_score"], errors="ignore").copy()


def _split_tokens(raw: str) -> set[str]:
    return {t.strip().lower() for t in str(raw).split(",") if t.strip()}


def _read_tile_list(path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        names.add(Path(line).stem)
    return names


def _ensure_point_columns(
    data: pd.DataFrame | gpd.GeoDataFrame,
    lon_col: str = "center_lon",
    lat_col: str = "center_lat",
) -> pd.DataFrame | gpd.GeoDataFrame:
    out = data.copy()
    has_lonlat = {lon_col, lat_col}.issubset(set(out.columns))
    if has_lonlat:
        out[lon_col] = pd.to_numeric(out[lon_col], errors="coerce")
        out[lat_col] = pd.to_numeric(out[lat_col], errors="coerce")
        missing = out[lon_col].isna() | out[lat_col].isna()
        if not bool(missing.any()):
            return out
        if "geometry" not in out.columns:
            return out

    if "geometry" not in out.columns:
        raise RuntimeError(
            f"Could not find coordinate columns '{lon_col}/{lat_col}' or geometry for point conversion."
        )

    if isinstance(out, gpd.GeoDataFrame):
        gdf = out.copy()
    else:
        gdf = gpd.GeoDataFrame(out.copy(), geometry="geometry")
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326", allow_override=True)
    else:
        gdf = gdf.to_crs("EPSG:4326")

    non_point = ~gdf.geometry.geom_type.isin(["Point"])
    if bool(non_point.any()):
        # Use projected CRS for geometric centroids, then return to lon/lat.
        tmp = gdf.to_crs("EPSG:3857")
        gdf = gdf.copy()
        gdf["geometry"] = tmp.geometry.centroid.to_crs("EPSG:4326")

    lon_vals = pd.to_numeric(gdf.geometry.x, errors="coerce")
    lat_vals = pd.to_numeric(gdf.geometry.y, errors="coerce")
    if has_lonlat:
        miss = gdf[lon_col].isna() | gdf[lat_col].isna()
        gdf.loc[miss, lon_col] = lon_vals.loc[miss]
        gdf.loc[miss, lat_col] = lat_vals.loc[miss]
    else:
        gdf[lon_col] = lon_vals
        gdf[lat_col] = lat_vals
    return gdf


def _write_tabular_or_vector(df: pd.DataFrame | gpd.GeoDataFrame, out_path: Path) -> None:
    ensure_dir(out_path.parent)
    ext = out_path.suffix.lower()
    if ext in GEO_EXTS:
        if isinstance(df, gpd.GeoDataFrame):
            gdf = df.copy()
        else:
            if not {"center_lon", "center_lat"}.issubset(set(df.columns)):
                raise RuntimeError("Vector output requires center_lon/center_lat columns.")
            gdf = gpd.GeoDataFrame(
                df.copy(),
                geometry=[Point(float(lon), float(lat)) for lon, lat in zip(df["center_lon"], df["center_lat"])],
                crs="EPSG:4326",
            )
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326", allow_override=True)
        else:
            gdf = gdf.to_crs("EPSG:4326")

        if ext == ".gpkg":
            gdf.to_file(out_path, driver="GPKG")
        elif ext == ".geojson":
            gdf.to_file(out_path, driver="GeoJSON")
        else:
            gdf.to_file(out_path)
        return

    if ext == ".parquet":
        pd.DataFrame(df).to_parquet(out_path, index=False)
    else:
        pd.DataFrame(df).to_csv(out_path, index=False)


def _nearest_candidates_haversine(
    candidates: pd.DataFrame,
    anchors: pd.DataFrame,
    same_tile_only: bool,
    tile_col: str,
    log,
) -> pd.DataFrame:
    if candidates.empty or anchors.empty:
        return pd.DataFrame(columns=["anchor_index", "candidate_index", "distance_m"])

    def _query_block(cand_part: pd.DataFrame, anchor_part: pd.DataFrame) -> list[dict]:
        cand_valid = cand_part.dropna(subset=["center_lon", "center_lat"])
        anchor_valid = anchor_part.dropna(subset=["center_lon", "center_lat"])
        if cand_valid.empty or anchor_valid.empty:
            return []

        cand_coords = np.deg2rad(np.c_[cand_valid["center_lat"].astype(float), cand_valid["center_lon"].astype(float)])
        anchor_coords = np.deg2rad(
            np.c_[anchor_valid["center_lat"].astype(float), anchor_valid["center_lon"].astype(float)]
        )
        cand_idx = cand_valid.index.to_numpy()
        anchor_idx = anchor_valid.index.to_numpy()

        try:
            from sklearn.neighbors import BallTree

            tree = BallTree(cand_coords, metric="haversine")
            dist, nn = tree.query(anchor_coords, k=1)
            d_m = dist[:, 0] * EARTH_RADIUS_M
            j = nn[:, 0]
        except Exception:
            d_m = np.zeros(len(anchor_coords), dtype=float)
            j = np.zeros(len(anchor_coords), dtype=int)
            for i, a in enumerate(anchor_coords):
                dlat = cand_coords[:, 0] - a[0]
                dlon = cand_coords[:, 1] - a[1]
                h = (
                    np.sin(dlat / 2.0) ** 2
                    + np.cos(a[0]) * np.cos(cand_coords[:, 0]) * np.sin(dlon / 2.0) ** 2
                )
                dists = 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))
                k = int(np.argmin(dists))
                d_m[i] = float(dists[k])
                j[i] = k

        rows = []
        for i in range(len(anchor_idx)):
            rows.append(
                {
                    "anchor_index": anchor_idx[i],
                    "candidate_index": cand_idx[int(j[i])],
                    "distance_m": float(d_m[i]),
                }
            )
        return rows

    out_rows: list[dict] = []
    if same_tile_only and tile_col in candidates.columns and tile_col in anchors.columns:
        cand_tile = candidates[tile_col].astype(str)
        anchor_tile = anchors[tile_col].astype(str)
        shared_tiles = sorted(set(cand_tile.unique()).intersection(set(anchor_tile.unique())))
        for tile in shared_tiles:
            c = candidates[cand_tile == tile]
            a = anchors[anchor_tile == tile]
            out_rows.extend(_query_block(c, a))
        log(f"Nearest matching by tile: shared_tiles={len(shared_tiles)}")
    else:
        if same_tile_only:
            log(
                f"[warn] same-tile nearest matching requested but '{tile_col}' missing; "
                "falling back to global nearest matching."
            )
        out_rows.extend(_query_block(candidates, anchors))

    return pd.DataFrame(out_rows)


def run_make_label_pack(args: argparse.Namespace) -> int:
    log = build_logger(args.log_file if args.log_file else "")
    candidates_path = Path(args.candidates)
    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)

    df = _load_candidates(candidates_path)
    if df.empty:
        raise RuntimeError(f"No rows in candidates table: {candidates_path}")
    rows_loaded = int(len(df))

    year_arg = int(getattr(args, "year", 0))
    if year_arg > 0 and "year" in df.columns:
        df = df[df["year"].astype(int) == year_arg].copy()
    tile_id_arg = str(getattr(args, "tile_id", "")).strip()
    if tile_id_arg and "tile_id" in df.columns:
        df = df[df["tile_id"].astype(str) == tile_id_arg].copy()
    tile_list_arg = str(getattr(args, "tile_list_file", "")).strip()
    if tile_list_arg:
        tile_list_path = Path(tile_list_arg)
        if not tile_list_path.exists():
            raise FileNotFoundError(f"Tile list file not found: {tile_list_path}")
        requested_tiles = _read_tile_list(tile_list_path)
        if "tile_id" not in df.columns:
            raise RuntimeError("Tile-list filtering requires a tile_id column in the candidates table.")
        df = df[df["tile_id"].astype(str).isin(requested_tiles)].copy()
    if df.empty:
        raise RuntimeError("No rows after year/tile filters.")

    region_mask_obj: RegionMask | None = None
    region_mask_arg = str(getattr(args, "region_mask", "")).strip()
    if region_mask_arg:
        region_path = Path(region_mask_arg)
        region_mask_obj = RegionMask.from_geojson(region_path)
        if not {"center_lon", "center_lat"}.issubset(set(df.columns)):
            raise RuntimeError("Region filtering requires center_lon and center_lat columns.")
        before = len(df)
        keep = region_mask_obj.contains_many(
            (float(lon), float(lat)) for lon, lat in zip(df["center_lon"], df["center_lat"])
        )
        df = df[np.array(keep, dtype=bool)].copy()
        log(
            f"Applied region mask ({region_path}): kept={len(df)} dropped={before - len(df)} "
            f"polygons={region_mask_obj.polygon_count}"
        )
        if df.empty:
            raise RuntimeError("No rows after region mask filter.")

    water_column = ""
    if bool(getattr(args, "exclude_water", False)):
        for c in ["ndwi_p50_center", "ndwi_p50"]:
            if c in df.columns:
                water_column = c
                break
        if not water_column:
            log("[warn] exclude-water requested but no NDWI column found (ndwi_p50_center/ndwi_p50); skipping water filter")
        else:
            before = len(df)
            w = pd.to_numeric(df[water_column], errors="coerce")
            water_thr = float(getattr(args, "water_ndwi_threshold", 0.0))
            keep = (w < water_thr) | w.isna()
            if bool(getattr(args, "water_drop_nan", False)):
                keep = (w < water_thr)
            df = df[keep].copy()
            log(
                f"Applied water filter ({water_column} < {water_thr}): "
                f"kept={len(df)} dropped={before - len(df)}"
            )
            if df.empty:
                raise RuntimeError("No rows after water filter.")

    sampling_mode = str(getattr(args, "sampling_mode", "stratified")).strip().lower()
    if sampling_mode == "top":
        picked = _top_confidence_sample(df, n=int(args.sample_n))
    elif sampling_mode == "random":
        if int(args.sample_n) <= 0 or len(df) <= int(args.sample_n):
            picked = df.copy()
        else:
            picked = df.sample(n=int(args.sample_n), random_state=int(args.seed)).copy()
    else:
        picked = _stratified_sample(df, n=int(args.sample_n), seed=int(args.seed))
    picked = picked.copy()
    picked["label"] = -1
    picked["review_status"] = "todo"
    picked["reviewer"] = ""
    picked["notes"] = ""

    csv_path = out_dir / "label_candidates.csv"
    picked.to_csv(csv_path, index=False)
    log(f"Wrote label CSV: {csv_path}")

    if "center_lon" in picked.columns and "center_lat" in picked.columns:
        gdf = gpd.GeoDataFrame(
            picked,
            geometry=[Point(float(lon), float(lat)) for lon, lat in zip(picked["center_lon"], picked["center_lat"])],
            crs="EPSG:4326",
        )
        gpkg_path = out_dir / "label_candidates.gpkg"
        gdf.to_file(gpkg_path, driver="GPKG")
        log(f"Wrote label GeoPackage: {gpkg_path}")

        radius_series = None
        if "radius_m" in picked.columns:
            radius_series = pd.to_numeric(picked["radius_m"], errors="coerce")
        elif {"radius_px", "pixel_size_m"}.issubset(set(picked.columns)):
            radius_series = (
                pd.to_numeric(picked["radius_px"], errors="coerce")
                * pd.to_numeric(picked["pixel_size_m"], errors="coerce")
            )

        if radius_series is not None and bool(radius_series.notna().any()):
            circle_df = picked.copy()
            circle_df["draft_radius_m"] = radius_series
            circle_df = circle_df[circle_df["draft_radius_m"].notna() & (circle_df["draft_radius_m"] > 0)].copy()
            circle_gdf = gpd.GeoDataFrame(
                circle_df,
                geometry=[
                    circle_polygon_wgs84(float(lon), float(lat), float(radius_m), n_points=int(args.circle_vertices))
                    for lon, lat, radius_m in zip(
                        circle_df["center_lon"], circle_df["center_lat"], circle_df["draft_radius_m"]
                    )
                ],
                crs="EPSG:4326",
            )
            circle_gpkg_path = out_dir / "label_candidate_circles.gpkg"
            circle_gdf.to_file(circle_gpkg_path, driver="GPKG")
            log(f"Wrote draft circle GeoPackage: {circle_gpkg_path}")
        else:
            circle_gpkg_path = None
            log("No usable radius information found; skipped draft circle GeoPackage.")
    else:
        gpkg_path = None
        circle_gpkg_path = None
        log("center_lon/center_lat not present; skipped GPKG export.")

    instructions = out_dir / "LABELING_INSTRUCTIONS.txt"
    instructions.write_text(
        (
            "Label values:\n"
            "  1 = true center pivot\n"
            "  0 = not a center pivot\n"
            " -1 = unlabeled (default)\n\n"
            "QGIS workflow:\n"
            "1) Open label_candidates.gpkg as centers and, if present,\n"
            "   label_candidate_circles.gpkg as draft circle polygons.\n"
            "2) Overlay on imagery.\n"
            "3) Edit field 'label' for each candidate.\n"
            "4) Save layer, then run:\n"
            "   python cpis.py qa build-train-table --labeled-input <your_file> --out-table data/training/cpi_train.csv\n"
        ),
        encoding="utf-8",
    )
    log(f"Wrote instructions: {instructions}")

    save_json(
        out_dir / "label_pack_summary.json",
        {
            "generated_at": utc_now_iso(),
            "source_candidates": str(candidates_path.resolve()),
            "rows_loaded": rows_loaded,
            "rows_total": int(len(df)),
            "rows_selected": int(len(picked)),
            "year_filter": year_arg if year_arg > 0 else None,
            "tile_id_filter": tile_id_arg if tile_id_arg else None,
            "tile_list_file": str(Path(tile_list_arg).resolve()) if tile_list_arg else "",
            "region_mask": str(Path(region_mask_arg).resolve()) if region_mask_arg else "",
            "exclude_water": bool(getattr(args, "exclude_water", False)),
            "water_ndwi_threshold": float(getattr(args, "water_ndwi_threshold", 0.0)),
            "water_drop_nan": bool(getattr(args, "water_drop_nan", False)),
            "water_column": water_column,
            "sampling_mode": sampling_mode,
            "label_csv": str(csv_path.resolve()),
            "label_gpkg": str(gpkg_path.resolve()) if gpkg_path else "",
            "label_circle_gpkg": str(circle_gpkg_path.resolve()) if circle_gpkg_path else "",
        },
    )
    return 0


def _load_labeled(path: Path, label_field: str) -> pd.DataFrame:
    loaded = _load_tabular_or_vector(path, keep_geometry=False)
    if isinstance(loaded, gpd.GeoDataFrame):
        if loaded.empty:
            return pd.DataFrame()
        df = pd.DataFrame(loaded.drop(columns=["geometry"], errors="ignore"))
    else:
        df = loaded

    if label_field != "label" and label_field in df.columns and "label" not in df.columns:
        df = df.rename(columns={label_field: "label"})
    return df


def run_transfer_anchor_labels(args: argparse.Namespace) -> int:
    log = build_logger(args.log_file if args.log_file else "")
    candidates_path = Path(args.candidates)
    anchors_path = Path(args.anchors)
    out_path = Path(args.out)
    summary_path = Path(args.summary_json) if str(args.summary_json).strip() else out_path.with_suffix(".summary.json")

    if not candidates_path.exists():
        raise FileNotFoundError(f"Candidates file not found: {candidates_path}")
    if not anchors_path.exists():
        raise FileNotFoundError(f"Anchors file not found: {anchors_path}")

    cand_loaded = _load_tabular_or_vector(candidates_path, keep_geometry=True)
    anc_loaded = _load_tabular_or_vector(anchors_path, keep_geometry=True)
    candidates = _ensure_point_columns(cand_loaded)
    anchors = _ensure_point_columns(anc_loaded)

    if candidates.empty:
        raise RuntimeError(f"No candidate rows loaded from {candidates_path}")
    if anchors.empty:
        raise RuntimeError(f"No anchor rows loaded from {anchors_path}")

    anchor_label_col = str(args.anchor_label_column).strip()
    anchor_positive_value = str(args.anchor_positive_value).strip()
    anchor_filter_applied = False
    if anchor_label_col and anchor_label_col in anchors.columns:
        a = anchors[anchor_label_col]
        try:
            target_num = float(anchor_positive_value)
            mask = pd.to_numeric(a, errors="coerce") == target_num
        except Exception:
            mask = a.astype(str).str.strip().str.lower() == anchor_positive_value.lower()
        anchors = anchors[mask].copy()
        anchor_filter_applied = True
    elif anchor_label_col:
        log(
            f"[warn] Anchor label column '{anchor_label_col}' not found; "
            "using all anchor rows as positive anchors."
        )

    if anchors.empty:
        raise RuntimeError("No anchor rows remain after anchor-label filtering.")

    tile_col = str(args.tile_column).strip() or "tile_id"
    same_tile_only = not bool(args.allow_cross_tile)
    matches = _nearest_candidates_haversine(
        candidates=candidates,
        anchors=anchors,
        same_tile_only=same_tile_only,
        tile_col=tile_col,
        log=log,
    )
    if matches.empty:
        raise RuntimeError("No nearest-neighbor matches produced between anchors and candidates.")

    max_distance_m = float(args.max_distance_m)
    matches = matches[matches["distance_m"] <= max_distance_m].copy()
    if matches.empty:
        log(f"[warn] No matches within max distance ({max_distance_m} m). Writing output with zero transfers.")

    if not matches.empty:
        best = matches.sort_values("distance_m").drop_duplicates(subset=["candidate_index"], keep="first")
    else:
        best = matches

    out = candidates.copy()
    label_col = str(args.candidate_label_column).strip() or "label"
    if label_col not in out.columns:
        out[label_col] = -1
    label_num = pd.to_numeric(out[label_col], errors="coerce")

    out["anchor_match"] = False
    out["anchor_distance_m"] = np.nan
    if str(args.anchor_id_column).strip() and str(args.anchor_id_column).strip() in anchors.columns:
        out["anchor_id"] = ""
        anchor_id_col = str(args.anchor_id_column).strip()
    else:
        out["anchor_id"] = ""
        anchor_id_col = ""

    if not best.empty:
        matched_idx = best["candidate_index"].tolist()
        out.loc[matched_idx, "anchor_match"] = True
        for _, row in best.iterrows():
            c_idx = row["candidate_index"]
            a_idx = row["anchor_index"]
            out.at[c_idx, "anchor_distance_m"] = float(row["distance_m"])
            if anchor_id_col:
                out.at[c_idx, "anchor_id"] = str(anchors.at[a_idx, anchor_id_col])
            else:
                out.at[c_idx, "anchor_id"] = str(a_idx)

        matched_mask = out["anchor_match"].astype(bool)
    else:
        matched_mask = pd.Series(False, index=out.index)

    if bool(args.only_unlabeled):
        updatable = ~label_num.isin([0, 1])
    else:
        updatable = pd.Series(True, index=out.index)
    transfer_mask = matched_mask & updatable
    out.loc[transfer_mask, label_col] = int(args.positive_label)

    review_col = str(args.review_status_column).strip()
    review_value = str(args.set_review_status).strip()
    if review_col and review_value:
        if review_col not in out.columns:
            out[review_col] = ""
        out.loc[transfer_mask, review_col] = review_value

    _write_tabular_or_vector(out, out_path)
    transferred = int(transfer_mask.sum())
    matched = int(matched_mask.sum())
    log(f"Wrote transferred labels: {out_path}")
    log(f"Anchor->candidate matches: matched={matched} transferred={transferred}")

    save_json(
        summary_path,
        {
            "generated_at": utc_now_iso(),
            "candidates": str(candidates_path.resolve()),
            "anchors": str(anchors_path.resolve()),
            "out": str(out_path.resolve()),
            "summary_json": str(summary_path.resolve()),
            "rows_candidates": int(len(candidates)),
            "rows_anchors_loaded": int(len(anc_loaded)),
            "rows_anchors_used": int(len(anchors)),
            "anchor_filter_applied": bool(anchor_filter_applied),
            "anchor_label_column": anchor_label_col,
            "anchor_positive_value": anchor_positive_value,
            "tile_column": tile_col,
            "same_tile_only": bool(same_tile_only),
            "max_distance_m": max_distance_m,
            "matches_within_distance": int(len(matches)),
            "candidates_matched": matched,
            "candidates_transferred": transferred,
            "candidate_label_column": label_col,
            "positive_label_value": int(args.positive_label),
            "only_unlabeled": bool(args.only_unlabeled),
            "review_status_column": review_col,
            "review_status_value": review_value,
        },
    )
    return 0


def run_build_train_table(args: argparse.Namespace) -> int:
    log = build_logger(args.log_file if args.log_file else "")
    labeled_path = Path(args.labeled_input)
    out_table = Path(args.out_table)
    ensure_dir(out_table.parent)

    df = _load_labeled(labeled_path, label_field=args.label_field)
    if df.empty:
        raise RuntimeError(f"No rows loaded from {labeled_path}")
    if "label" not in df.columns:
        raise RuntimeError(f"Label field not found. Expected '{args.label_field}' or 'label'.")

    work = df.copy()
    work["label"] = pd.to_numeric(work["label"], errors="coerce")
    edge_col = str(args.edge_status_column).strip()
    edge_values = _split_tokens(args.edge_status_values)
    if edge_col and edge_col in work.columns and edge_values:
        work["_is_edge"] = (
            work[edge_col]
            .astype(str)
            .str.strip()
            .str.lower()
            .isin(edge_values)
        )
    else:
        work["_is_edge"] = False

    edge_policy = str(args.edge_policy).strip().lower()
    if edge_policy == "drop":
        work = work[~work["_is_edge"]].copy()
    elif edge_policy in {"positive", "negative"}:
        unresolved = work["_is_edge"] & ~work["label"].isin([0, 1])
        work.loc[unresolved, "label"] = 1 if edge_policy == "positive" else 0

    work = work[work["label"].isin([0, 1])].copy()
    work["label"] = work["label"].astype(int)
    if work.empty:
        raise RuntimeError("No labeled rows with label in {0,1}.")

    req_cols = [c for c in DEFAULT_FEATURE_COLUMNS if c in work.columns]
    if len(req_cols) < 3:
        raise RuntimeError(
            "Insufficient feature columns found in labeled input. "
            f"Need at least 3 of {DEFAULT_FEATURE_COLUMNS}"
        )

    if args.deduplicate and {"tile_id", "x", "y", "radius_px"}.issubset(set(work.columns)):
        work = work.drop_duplicates(subset=["tile_id", "x", "y", "radius_px"])

    meta_cols: list[str] = [c for c in ["year", "tile_id", "center_lon", "center_lat", "radius_m"] if c in work.columns]
    if bool(args.keep_review_status) and edge_col and edge_col in work.columns:
        meta_cols.append(edge_col)
    if bool(args.keep_is_edge):
        meta_cols.append("_is_edge")

    keep_cols = sorted(set(req_cols + ["label"] + meta_cols))
    out_df = work[keep_cols].dropna(subset=req_cols + ["label"]).copy()

    if bool(args.emit_sample_weight):
        edge_weight = float(args.edge_weight)
        sw_col = str(args.sample_weight_column).strip() or "sample_weight"
        out_df[sw_col] = 1.0
        if "_is_edge" in out_df.columns:
            out_df.loc[out_df["_is_edge"].astype(bool), sw_col] = edge_weight

    if "_is_edge" in out_df.columns and not bool(args.keep_is_edge):
        out_df = out_df.drop(columns=["_is_edge"])
    elif "_is_edge" in out_df.columns and bool(args.keep_is_edge):
        out_df = out_df.rename(columns={"_is_edge": "is_edge"})

    fmt = "csv"
    if out_table.suffix.lower() == ".parquet":
        try:
            out_df.to_parquet(out_table, index=False)
            fmt = "parquet"
        except Exception as exc:
            log(f"[warn] parquet write failed ({exc}); writing CSV fallback")
            out_table = out_table.with_suffix(".csv")
            out_df.to_csv(out_table, index=False)
            fmt = "csv"
    else:
        out_df.to_csv(out_table, index=False)

    summary = {
        "generated_at": utc_now_iso(),
        "labeled_input": str(labeled_path.resolve()),
        "out_table": str(out_table.resolve()),
        "format": fmt,
        "rows_out": int(len(out_df)),
        "label_1": int((out_df["label"] == 1).sum()),
        "label_0": int((out_df["label"] == 0).sum()),
        "feature_columns": req_cols,
        "edge_policy": edge_policy,
        "edge_status_column": edge_col,
        "edge_status_values": sorted(edge_values),
        "edge_rows_out": int(out_df.get("is_edge", pd.Series(dtype=bool)).sum()) if "is_edge" in out_df.columns else 0,
        "emit_sample_weight": bool(args.emit_sample_weight),
        "sample_weight_column": str(args.sample_weight_column).strip() if bool(args.emit_sample_weight) else "",
        "edge_weight": float(args.edge_weight),
    }
    save_json(out_table.with_suffix(".summary.json"), summary)
    log(f"Wrote training table: {out_table}")
    return 0


def build_parser(subparsers) -> None:
    p1 = subparsers.add_parser("make-label-pack", help="Create a label pack (CSV + GPKG) from candidate detections")
    p1.add_argument("--candidates", required=True, help="Candidates table path")
    p1.add_argument("--out-dir", default="runs/labeling", help="Output label pack directory")
    p1.add_argument("--sample-n", type=int, default=300, help="Max candidates to sample for labeling")
    p1.add_argument("--year", type=int, default=0, help="Optional year filter; 0 disables year filtering")
    p1.add_argument("--tile-id", default="", help="Optional exact tile_id filter")
    p1.add_argument("--tile-list-file", default="", help="Optional newline-delimited list of tile_ids to keep")
    p1.add_argument("--region-mask", default="", help="Optional GeoJSON region mask to drop ocean/out-of-scope points")
    p1.add_argument("--exclude-water", action="store_true", help="Drop likely-water candidates using NDWI field")
    p1.add_argument("--water-ndwi-threshold", type=float, default=0.0, help="Water threshold; keep NDWI < this value")
    p1.add_argument("--water-drop-nan", action="store_true", help="Drop rows with missing NDWI when exclude-water is enabled")
    p1.add_argument(
        "--sampling-mode",
        default="stratified",
        choices=["stratified", "top", "random"],
        help="How to choose the review subset; use 'top' for obvious high-confidence circles",
    )
    p1.add_argument("--circle-vertices", type=int, default=64, help="Vertex count for draft candidate circle polygons")
    p1.add_argument("--seed", type=int, default=42, help="Sampling seed")
    p1.add_argument("--log-file", default="", help="Optional log file")
    p1.set_defaults(func=run_make_label_pack)

    p2 = subparsers.add_parser("build-train-table", help="Convert labeled candidates into model training table")
    p2.add_argument("--labeled-input", required=True, help="Labeled CSV/Parquet/GPKG/SHP path")
    p2.add_argument("--label-field", default="label", help="Label field name in input")
    p2.add_argument("--out-table", default="data/training/cpi_train.csv", help="Output training table path")
    p2.add_argument("--deduplicate", action="store_true", help="Drop duplicate candidate rows where possible")
    p2.add_argument("--edge-status-column", default="review_status", help="Column containing edge/ambiguous review status")
    p2.add_argument("--edge-status-values", default="edge", help="Comma-separated values treated as edge status")
    p2.add_argument(
        "--edge-policy",
        default="ignore",
        choices=["ignore", "positive", "negative", "drop"],
        help="How to handle edge-status rows with unresolved labels",
    )
    p2.add_argument("--emit-sample-weight", action="store_true", help="Emit sample weight column for edge-aware training")
    p2.add_argument("--sample-weight-column", default="sample_weight", help="Output sample weight column name")
    p2.add_argument("--edge-weight", type=float, default=0.5, help="Sample weight assigned to edge rows")
    p2.add_argument("--keep-review-status", action="store_true", help="Keep review status column in output table")
    p2.add_argument("--keep-is-edge", action="store_true", help="Keep derived is_edge boolean column in output table")
    p2.add_argument("--log-file", default="", help="Optional log file")
    p2.set_defaults(func=run_build_train_table)

    p3 = subparsers.add_parser(
        "transfer-anchor-labels",
        help="Transfer positive labels from manual anchor points to nearest candidate points",
    )
    p3.add_argument("--candidates", required=True, help="Candidate table/vector path")
    p3.add_argument("--anchors", required=True, help="Manual anchor points path")
    p3.add_argument("--out", required=True, help="Output table/vector path with transferred labels")
    p3.add_argument("--summary-json", default="", help="Optional output summary JSON path")
    p3.add_argument("--max-distance-m", type=float, default=250.0, help="Maximum anchor-to-candidate transfer distance")
    p3.add_argument("--tile-column", default="tile_id", help="Tile ID column for same-tile matching")
    p3.add_argument("--allow-cross-tile", action="store_true", help="Allow nearest matching across tile boundaries")
    p3.add_argument("--anchor-label-column", default="label", help="Anchor label column; if missing all anchors are used")
    p3.add_argument("--anchor-positive-value", default="1", help="Anchor label value treated as positive")
    p3.add_argument("--anchor-id-column", default="", help="Optional anchor ID column to copy into anchor_id")
    p3.add_argument("--candidate-label-column", default="label", help="Candidate label column to update")
    p3.add_argument("--positive-label", type=int, default=1, help="Label value written to matched candidates")
    p3.add_argument("--only-unlabeled", action="store_true", help="Update only candidates not already labeled 0/1")
    p3.add_argument("--review-status-column", default="review_status", help="Review status column to update")
    p3.add_argument("--set-review-status", default="anchor", help="Review status value for transferred rows")
    p3.add_argument("--log-file", default="", help="Optional log file")
    p3.set_defaults(func=run_transfer_anchor_labels)
