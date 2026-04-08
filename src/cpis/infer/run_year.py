"""Run year inference from candidate table and trained model."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from cpis.common.constants import DEFAULT_FINAL_CENTERS_TEMPLATE, DEFAULT_FINAL_SHAPEFILE_TEMPLATE
from cpis.common.file_utils import ensure_dir, save_json
from cpis.common.geo_utils import circle_polygon_wgs84
from cpis.common.lock_utils import manifest_lock
from cpis.common.logging_utils import build_logger
from cpis.common.time_utils import utc_now_iso


def _load_candidates(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Candidates table not found: {path}")
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _load_model(model_path: Path) -> tuple[str, Any]:
    if model_path.suffix.lower() == ".json" and model_path.name.endswith(".meta.json"):
        import json

        with model_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        actual = Path(meta["model_path"])
        model_type = str(meta["model_type"])
        return _load_model_with_type(actual, model_type)
    return _load_model_with_type(model_path, "")


def _load_model_with_type(path: Path, hinted_type: str) -> tuple[str, Any]:
    path = Path(path)
    model_type = hinted_type.lower().strip()
    if model_type == "xgboost" or (not model_type and path.suffix.lower() == ".json"):
        from xgboost import XGBClassifier

        model = XGBClassifier()
        model.load_model(str(path))
        return "xgboost", model

    try:
        import joblib
    except ModuleNotFoundError as exc:
        raise RuntimeError("Missing dependency 'joblib' required to load non-xgboost models.") from exc
    model = joblib.load(path)
    if not model_type:
        model_type = "joblib"
    return model_type, model


def _score_candidates(model, model_type: str, X: np.ndarray) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(X)[:, 1], dtype=np.float32)
    if hasattr(model, "decision_function"):
        raw = np.asarray(model.decision_function(X), dtype=np.float32)
        mn, mx = float(np.min(raw)), float(np.max(raw))
        if mx <= mn:
            return np.zeros(raw.shape[0], dtype=np.float32)
        return (raw - mn) / (mx - mn)
    raise RuntimeError(f"Unsupported model scoring interface for model_type={model_type}")


def _country_join(gdf: gpd.GeoDataFrame, country_path: Path, country_field: str, log) -> gpd.GeoDataFrame:
    if not country_path.exists():
        raise FileNotFoundError(f"Country boundary file not found: {country_path}")
    countries = gpd.read_file(country_path)
    if countries.crs is None:
        countries = countries.set_crs("EPSG:4326")
    elif str(countries.crs).upper() != "EPSG:4326":
        countries = countries.to_crs("EPSG:4326")

    if country_field not in countries.columns:
        raise RuntimeError(f"Country field '{country_field}' not found in {country_path}")

    joined = gpd.sjoin(gdf, countries[[country_field, "geometry"]], how="left", predicate="intersects")
    joined["country"] = joined[country_field].astype(str).replace({"nan": "unknown"})
    joined = joined.drop(columns=[country_field, "index_right"], errors="ignore")
    log(f"Country join complete; matched={int((joined['country'] != 'unknown').sum())} / {len(joined)}")
    return joined


def _prepare_feature_matrix(df: pd.DataFrame, columns: list[str]) -> np.ndarray:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise RuntimeError(f"Candidates table missing feature columns required by model: {missing}")
    return df[columns].astype(float).values


def _policy_key(mode: str) -> str:
    m = mode.strip().lower()
    mapping = {
        "precision-first": "precision_first",
        "balanced": "balanced",
        "recall-first": "recall_first",
    }
    if m not in mapping:
        raise RuntimeError(f"Unsupported threshold mode: {mode}")
    return mapping[m]


def _resolve_threshold(args: argparse.Namespace, model_path: Path, log) -> tuple[float, str, str]:
    mode = str(args.threshold_mode).strip().lower()
    if mode == "manual":
        return float(args.threshold), "manual", ""

    report_path = Path(args.calibration_report) if args.calibration_report else None
    if report_path is None:
        if model_path.suffix.lower() == ".json" and model_path.name.endswith(".meta.json"):
            with model_path.open("r", encoding="utf-8") as f:
                meta = json.load(f)
            rp = meta.get("report_path", "")
            if rp:
                report_path = Path(rp)

    if report_path is None or not report_path.exists():
        raise RuntimeError(
            f"threshold-mode={mode} requires calibration report. "
            "Pass --calibration-report or use model meta JSON with report_path."
        )

    with report_path.open("r", encoding="utf-8") as f:
        report = json.load(f)
    policies = report.get("threshold_policies", {})
    key = _policy_key(mode)
    if key not in policies:
        raise RuntimeError(f"Policy key '{key}' not found in report: {report_path}")
    thr = float(policies[key])
    log(f"Using threshold mode={mode}, threshold={thr} from {report_path}")
    return thr, mode, str(report_path.resolve())


def run_infer_year(args: argparse.Namespace) -> int:
    log = build_logger(args.log_file if args.log_file else "")
    year = int(args.year)
    candidates_path = Path(args.candidates)
    model_path = Path(args.model)
    out_root = Path(args.out_dir) if args.out_dir else (Path("outputs") / f"year_{year}")
    ensure_dir(out_root)
    ensure_dir(out_root / "tiles")
    ensure_dir(Path("outputs") / "final")

    df = _load_candidates(candidates_path)
    if df.empty:
        raise RuntimeError("Candidate table is empty.")
    if "year" in df.columns:
        df = df[df["year"].astype(int) == year].copy()
    if df.empty:
        raise RuntimeError(f"No candidate rows for year={year} in {candidates_path}")

    model_type, model = _load_model(model_path)
    feature_cols = (
        [c.strip() for c in args.feature_columns.split(",") if c.strip()]
        if args.feature_columns
        else ["geom_score", "ndvi_amp", "ring_contrast", "texture_score", "radius_m", "radius_px", "pixel_size_m"]
    )
    X = _prepare_feature_matrix(df, feature_cols)
    score = _score_candidates(model, model_type, X)
    df["confidence"] = score.astype(np.float32)

    thr, threshold_mode_used, threshold_report_path = _resolve_threshold(args, model_path, log)
    keep = df[df["confidence"] >= thr].copy()
    if keep.empty:
        log(f"No detections above threshold={thr}. Writing empty outputs.")

    keep["det_id"] = [f"{year}_{i}_{uuid.uuid4().hex[:8]}" for i in range(len(keep))]
    keep["area_ha"] = np.pi * (keep["radius_m"].astype(float) ** 2) / 10000.0
    keep["source"] = args.source_model
    keep["country"] = "unknown"

    if len(keep) > 0:
        keep["geometry"] = keep.apply(
            lambda r: circle_polygon_wgs84(float(r["center_lon"]), float(r["center_lat"]), float(r["radius_m"]), n_points=64),
            axis=1,
        )
        gdf = gpd.GeoDataFrame(keep, geometry="geometry", crs="EPSG:4326")
    else:
        gdf = gpd.GeoDataFrame(keep, geometry=[], crs="EPSG:4326")

    if args.country_boundary:
        gdf = _country_join(gdf, Path(args.country_boundary), args.country_field, log)

    lock_path = out_root / ".inference.lock.json"
    with manifest_lock(lock_path=lock_path, stale_seconds=int(args.stale_lock_seconds), force=bool(args.force_lock)):
        # Write per-tile internal files.
        if not gdf.empty:
            for tile_id, part in gdf.groupby("tile_id"):
                tile_path = out_root / "tiles" / f"{tile_id}.gpkg"
                part.to_file(tile_path, driver="GPKG")

        # Final shapefile fields constrained for DBF compatibility.
        shp_cols = [
            "det_id",
            "year",
            "confidence",
            "radius_m",
            "area_ha",
            "tile_id",
            "country",
            "source",
            "center_lon",
            "center_lat",
            "geometry",
        ]
        final_gdf = gdf.copy()
        if "year" not in final_gdf.columns:
            final_gdf["year"] = year
        final_gdf = final_gdf[shp_cols]
        final_gdf = final_gdf.rename(
            columns={
                "confidence": "conf",
                "center_lon": "ctr_lon",
                "center_lat": "ctr_lat",
            }
        )

        out_shp = Path(args.out_shp) if args.out_shp else (Path("outputs") / "final" / DEFAULT_FINAL_SHAPEFILE_TEMPLATE.format(year=year))
        ensure_dir(out_shp.parent)
        if out_shp.exists():
            for ext in [".shp", ".dbf", ".shx", ".prj", ".cpg"]:
                p = out_shp.with_suffix(ext)
                if p.exists():
                    p.unlink()
        final_gdf.to_file(out_shp)
        log(f"Wrote final detections shapefile: {out_shp}")

        if args.write_centers:
            centers = gdf.copy()
            centers["geometry"] = centers.apply(lambda r: Point(float(r["center_lon"]), float(r["center_lat"])), axis=1)
            center_shp = Path(args.centers_shp) if args.centers_shp else (
                Path("outputs") / "final" / DEFAULT_FINAL_CENTERS_TEMPLATE.format(year=year)
            )
            ensure_dir(center_shp.parent)
            if center_shp.exists():
                for ext in [".shp", ".dbf", ".shx", ".prj", ".cpg"]:
                    p = center_shp.with_suffix(ext)
                    if p.exists():
                        p.unlink()
            centers[["det_id", "year", "confidence", "radius_m", "tile_id", "country", "source", "geometry"]].rename(
                columns={"confidence": "conf"}
            ).to_file(center_shp)
            log(f"Wrote centers shapefile: {center_shp}")

        summary = {
            "generated_at": utc_now_iso(),
            "year": year,
            "model_path": str(model_path.resolve()),
            "model_type": model_type,
            "candidates_path": str(candidates_path.resolve()),
            "threshold": thr,
            "threshold_mode": threshold_mode_used,
            "threshold_report_path": threshold_report_path,
            "candidate_rows": int(len(df)),
            "detections_rows": int(len(gdf)),
            "output_shp": str(out_shp.resolve()),
        }
        save_json(out_root / "inference_summary.json", summary)
    return 0


def build_parser(subparsers) -> None:
    p = subparsers.add_parser("run-year", help="Score candidates and write yearly shapefiles")
    p.add_argument("--year", type=int, required=True, help="Year")
    p.add_argument("--candidates", required=True, help="Candidates table path")
    p.add_argument("--model", required=True, help="Model path or model meta JSON path")
    p.add_argument("--threshold", type=float, default=0.5, help="Confidence threshold")
    p.add_argument(
        "--threshold-mode",
        default="manual",
        choices=["manual", "precision-first", "balanced", "recall-first"],
        help="Threshold policy. For non-manual modes, a calibration report is required.",
    )
    p.add_argument("--calibration-report", default="", help="Calibration report JSON path")
    p.add_argument("--feature-columns", default="", help="Comma-separated feature columns override")
    p.add_argument("--source-model", default="cpi_candidate_classifier_v1", help="Source model label")
    p.add_argument("--out-dir", default="", help="Output directory (default: outputs/year_{year})")
    p.add_argument("--out-shp", default="", help="Final yearly shapefile path")
    p.add_argument("--write-centers", action="store_true", help="Also write centers point shapefile")
    p.add_argument("--centers-shp", default="", help="Centers shapefile output path")
    p.add_argument("--country-boundary", default="", help="Optional boundary file for country attribution")
    p.add_argument("--country-field", default="ADMIN", help="Country field in boundary file")
    p.add_argument("--stale-lock-seconds", type=int, default=7200, help="Lock recovery timeout")
    p.add_argument("--force-lock", action="store_true", help="Force lock takeover")
    p.add_argument("--log-file", default="", help="Optional log file path")
    p.set_defaults(func=run_infer_year)
