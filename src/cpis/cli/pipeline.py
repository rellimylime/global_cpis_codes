"""Convenience pipeline orchestration commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from cpis.features.generate_candidates import run_generate_candidates
from cpis.infer.run_year import run_infer_year
from cpis.qa.report_year import run_report_year


def run_pipeline_year(args: argparse.Namespace) -> int:
    year = int(args.year)
    feature_out = Path(args.feature_out) if args.feature_out else Path("runs") / "features" / str(year)
    detections_out = Path(args.out_shp) if args.out_shp else (Path("outputs") / "final" / f"cpis_arid_ssa_{year}.shp")

    feature_args = argparse.Namespace(
        year=year,
        input_dir=args.input_dir,
        out_dir=str(feature_out),
        manifest=args.feature_manifest,
        resume=args.resume,
        min_radius_m=args.min_radius_m,
        max_radius_m=args.max_radius_m,
        hough_dp=args.hough_dp,
        min_dist_px=args.min_dist_px,
        hough_param1=args.hough_param1,
        hough_param2=args.hough_param2,
        canny_low=args.canny_low,
        canny_high=args.canny_high,
        nms_iou=args.nms_iou,
        max_candidates_per_tile=args.max_candidates_per_tile,
        region_mask=args.region_mask,
        exclude_water=args.exclude_water,
        water_ndwi_threshold=args.water_ndwi_threshold,
        max_tiles=args.max_tiles,
        stale_lock_seconds=args.stale_lock_seconds,
        force_lock=args.force_lock,
        log_file=args.log_file,
    )
    run_generate_candidates(feature_args)

    infer_args = argparse.Namespace(
        year=year,
        candidates=str(feature_out / "candidates.parquet") if (feature_out / "candidates.parquet").exists() else str(feature_out / "candidates.csv"),
        model=args.model,
        threshold=args.threshold,
        threshold_mode=args.threshold_mode,
        calibration_report=args.calibration_report,
        feature_columns=args.feature_columns,
        source_model=args.source_model,
        out_dir=args.infer_out_dir,
        out_shp=str(detections_out),
        write_centers=args.write_centers,
        centers_shp=args.centers_shp,
        country_boundary=args.country_boundary,
        country_field=args.country_field,
        stale_lock_seconds=args.stale_lock_seconds,
        force_lock=args.force_lock,
        log_file=args.log_file,
    )
    if str(args.stop_after).lower() == "features":
        return 0

    run_infer_year(infer_args)
    if str(args.stop_after).lower() == "infer":
        return 0

    if not args.skip_qa:
        qa_args = argparse.Namespace(
            year=year,
            detections=str(detections_out),
            out_dir=args.qa_out_dir,
            sample_n=args.qa_sample_n,
            compare_to=args.compare_to,
            plot_hist=args.plot_hist,
            log_file=args.log_file,
        )
        run_report_year(qa_args)
    return 0


def build_parser(subparsers) -> None:
    p = subparsers.add_parser("run-year", help="Run feature generation + inference + QA for a year")
    p.add_argument("--year", type=int, required=True, help="Year")
    p.add_argument("--input-dir", required=True, help="Input composite directory for the target year")
    p.add_argument("--model", required=True, help="Model path or model meta JSON")
    p.add_argument("--threshold", type=float, default=0.5, help="Inference threshold")
    p.add_argument(
        "--threshold-mode",
        default="precision-first",
        choices=["manual", "precision-first", "balanced", "recall-first"],
        help="Inference threshold policy (default: precision-first)",
    )
    p.add_argument("--calibration-report", default="", help="Calibration report JSON path (optional with model meta)")
    p.add_argument("--feature-columns", default="", help="Feature columns override for inference")
    p.add_argument("--source-model", default="cpi_candidate_classifier_v1", help="Source model label")
    p.add_argument("--resume", action="store_true", help="Resume feature generation")
    p.add_argument("--feature-out", default="", help="Feature output dir (default: runs/features/{year})")
    p.add_argument("--feature-manifest", default="", help="Feature manifest path override")
    p.add_argument("--infer-out-dir", default="", help="Inference output dir (default: outputs/year_{year})")
    p.add_argument("--out-shp", default="", help="Final detections shapefile path")
    p.add_argument("--write-centers", action="store_true", help="Write center points shapefile")
    p.add_argument("--centers-shp", default="", help="Centers shapefile path")
    p.add_argument("--country-boundary", default="", help="Optional country boundary file")
    p.add_argument("--country-field", default="ADMIN", help="Country field name")
    p.add_argument("--skip-qa", action="store_true", help="Skip QA report stage")
    p.add_argument("--qa-out-dir", default="runs/reports", help="QA report output dir")
    p.add_argument("--qa-sample-n", type=int, default=100, help="QA sample size")
    p.add_argument("--compare-to", default="", help="Optional compare shapefile for drift check")
    p.add_argument("--plot-hist", action="store_true", help="Write QA histogram PNGs")
    p.add_argument("--min-radius-m", type=float, default=150.0, help="Feature generation min radius")
    p.add_argument("--max-radius-m", type=float, default=2500.0, help="Feature generation max radius")
    p.add_argument("--hough-dp", type=float, default=1.2, help="Hough dp")
    p.add_argument("--min-dist-px", type=float, default=20.0, help="Hough min center distance")
    p.add_argument("--hough-param1", type=float, default=100.0, help="Hough param1")
    p.add_argument("--hough-param2", type=float, default=18.0, help="Hough param2")
    p.add_argument("--canny-low", type=float, default=50.0, help="Canny low")
    p.add_argument("--canny-high", type=float, default=150.0, help="Canny high")
    p.add_argument("--nms-iou", type=float, default=0.35, help="Circle NMS IoU")
    p.add_argument("--max-candidates-per-tile", type=int, default=300, help="Max candidates per tile")
    p.add_argument("--region-mask", default="assets/regions/arid_ssa.geojson", help="GeoJSON region mask to keep land/arid points")
    p.add_argument("--exclude-water", action="store_true", help="Drop candidates likely on water via NDWI threshold")
    p.add_argument("--water-ndwi-threshold", type=float, default=0.0, help="NDWI threshold for water exclusion")
    p.add_argument("--max-tiles", type=int, default=0, help="Limit tiles for smoke runs")
    p.add_argument(
        "--stop-after",
        default="qa",
        choices=["features", "infer", "qa"],
        help="Stop pipeline after this stage for validation checkpoints",
    )
    p.add_argument("--stale-lock-seconds", type=int, default=7200, help="Stale lock timeout")
    p.add_argument("--force-lock", action="store_true", help="Force lock takeover")
    p.add_argument("--log-file", default="", help="Optional shared log file")
    p.set_defaults(func=run_pipeline_year)
