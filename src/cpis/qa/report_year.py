"""Generate yearly QA report for CPI detections."""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from cpis.common.file_utils import ensure_dir, save_json
from cpis.common.logging_utils import build_logger
from cpis.common.time_utils import utc_now_iso


def _safe_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _save_histogram_plot(series: pd.Series, path: Path, title: str, bins: int = 30) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    values = pd.to_numeric(series, errors="coerce").dropna().values
    if len(values) == 0:
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(values, bins=bins)
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _save_histogram_csv(series: pd.Series, path: Path, bins: int = 30) -> None:
    values = pd.to_numeric(series, errors="coerce").dropna().values
    if len(values) == 0:
        pd.DataFrame(columns=["bin_left", "bin_right", "count"]).to_csv(path, index=False)
        return
    counts, edges = np.histogram(values, bins=bins)
    out = pd.DataFrame(
        {
            "bin_left": edges[:-1],
            "bin_right": edges[1:],
            "count": counts.astype(int),
        }
    )
    out.to_csv(path, index=False)


def run_report_year(args: argparse.Namespace) -> int:
    log = build_logger(args.log_file if args.log_file else "")
    year = int(args.year)
    detections_path = Path(args.detections)
    if not detections_path.exists():
        raise FileNotFoundError(f"Detections vector not found: {detections_path}")

    gdf = gpd.read_file(detections_path)
    if gdf.empty:
        raise RuntimeError(f"Detections file is empty: {detections_path}")

    out_dir = Path(args.out_dir) if args.out_dir else (Path("runs") / "reports")
    ensure_dir(out_dir)

    # Normalize expected columns across shapefile naming constraints.
    conf_col = "conf" if "conf" in gdf.columns else ("confidence" if "confidence" in gdf.columns else None)
    radius_col = "radius_m" if "radius_m" in gdf.columns else None
    country_col = "country" if "country" in gdf.columns else None

    conf_values = gdf[conf_col].astype(float) if conf_col else pd.Series(dtype=float)
    radius_values = gdf[radius_col].astype(float) if radius_col else pd.Series(dtype=float)

    detections_total = int(len(gdf))
    mean_conf = _safe_float(conf_values.mean(), 0.0) if conf_col else None
    mean_radius = _safe_float(radius_values.mean(), 0.0) if radius_col else None
    p10_radius = _safe_float(radius_values.quantile(0.10), 0.0) if radius_col else None
    p90_radius = _safe_float(radius_values.quantile(0.90), 0.0) if radius_col else None

    by_country_csv = out_dir / f"report_{year}_country_counts.csv"
    if country_col:
        country_counts = gdf.groupby(country_col, dropna=False).size().reset_index(name="count").sort_values("count", ascending=False)
        country_counts.to_csv(by_country_csv, index=False)
    else:
        country_counts = pd.DataFrame(columns=["country", "count"])

    # Random QA sample for manual visual inspection queue.
    sample_n = min(int(args.sample_n), detections_total)
    qa_sample = gdf.sample(n=sample_n, random_state=42).copy()
    qa_sample_csv = out_dir / f"report_{year}_qa_sample.csv"
    qa_sample.drop(columns=["geometry"], errors="ignore").to_csv(qa_sample_csv, index=False)

    if conf_col:
        conf_hist_csv = out_dir / f"report_{year}_conf_hist.csv"
        _save_histogram_csv(conf_values, conf_hist_csv, bins=30)
        if args.plot_hist:
            _save_histogram_plot(conf_values, out_dir / f"report_{year}_conf_hist.png", title=f"Confidence Histogram ({year})")
    else:
        conf_hist_csv = None
    if radius_col:
        radius_hist_csv = out_dir / f"report_{year}_radius_hist.csv"
        _save_histogram_csv(radius_values, radius_hist_csv, bins=30)
        if args.plot_hist:
            _save_histogram_plot(radius_values, out_dir / f"report_{year}_radius_hist.png", title=f"Radius Histogram ({year})")
    else:
        radius_hist_csv = None

    report = {
        "generated_at": utc_now_iso(),
        "year": year,
        "detections_path": str(detections_path.resolve()),
        "detections_total": detections_total,
        "mean_confidence": mean_conf,
        "mean_radius_m": mean_radius,
        "radius_p10_m": p10_radius,
        "radius_p90_m": p90_radius,
        "conf_hist_csv": str(conf_hist_csv.resolve()) if conf_hist_csv else "",
        "radius_hist_csv": str(radius_hist_csv.resolve()) if radius_hist_csv else "",
        "country_breakdown_csv": str(by_country_csv.resolve()) if country_col else "",
        "qa_sample_csv": str(qa_sample_csv.resolve()),
        "qa_sample_n": int(sample_n),
    }

    # Optional drift comparison.
    if args.compare_to:
        compare_path = Path(args.compare_to)
        if compare_path.exists():
            compare = gpd.read_file(compare_path)
            report["compare_to"] = str(compare_path.resolve())
            report["compare_to_count"] = int(len(compare))
            report["count_delta"] = int(detections_total - len(compare))
        else:
            log(f"[warn] compare_to path not found: {compare_path}")

    report_path = out_dir / f"report_{year}.json"
    save_json(report_path, report)
    log(f"Wrote QA report: {report_path}")
    return 0


def build_parser(subparsers) -> None:
    p = subparsers.add_parser("report-year", help="Generate QA summary report for one year")
    p.add_argument("--year", type=int, required=True, help="Year")
    p.add_argument("--detections", required=True, help="Detections shapefile path")
    p.add_argument("--out-dir", default="", help="Report output directory")
    p.add_argument("--sample-n", type=int, default=100, help="Random detections to include in QA sample CSV")
    p.add_argument("--compare-to", default="", help="Optional reference detections shapefile for drift check")
    p.add_argument("--plot-hist", action="store_true", help="Also write histogram PNGs (off by default)")
    p.add_argument("--log-file", default="", help="Optional log file")
    p.set_defaults(func=run_report_year)
