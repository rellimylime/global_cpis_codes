import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime

try:
    from osgeo import ogr
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency 'osgeo' (GDAL). Run with the CPI detection environment.") from exc


def utc_now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    print(f"[{utc_now()}Z] {msg}", flush=True)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def load_json(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def threshold_text(value):
    return format(float(value), "g")


def threshold_tag(value):
    return threshold_text(value).replace(".", "p").replace("-", "m")


def scale_tag(value):
    return threshold_text(value).replace(".", "p").replace("-", "m")


def run_cmd(cmd, log_path):
    ensure_dir(os.path.dirname(log_path) or ".")
    log(f"RUN: {' '.join(cmd)}")
    with open(log_path, "w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            print(line, flush=True)
            log_file.write(line + "\n")
        rc = proc.wait()
    log(f"EXIT {rc}: {log_path}")
    return rc


def shp_feature_count(path):
    if not os.path.exists(path):
        return 0
    ds = ogr.Open(path)
    if ds is None:
        return 0
    lyr = ds.GetLayer(0)
    count = int(lyr.GetFeatureCount())
    ds = None
    return count


def threshold_summary_map(summary_json_path):
    data = load_json(summary_json_path, {})
    out = {}
    for row in data.get("summary", {}).get("thresholds", []):
        key = str(row.get("threshold"))
        out[key] = row
    return out


def upsert_rows(existing_rows, new_rows):
    by_setting = {}
    for row in existing_rows:
        key = row.get("setting")
        if key:
            by_setting[key] = row
    for row in new_rows:
        key = row.get("setting")
        if key:
            by_setting[key] = row
    rows = list(by_setting.values())
    rows.sort(key=lambda r: str(r.get("setting", "")))
    return rows


def count_union_mask_tifs(result_dir):
    total = 0
    if not os.path.isdir(result_dir):
        return 0
    for root, _, files in os.walk(result_dir):
        for fn in files:
            lower = fn.lower()
            if lower.endswith(".tif") and "union_segm_" in lower:
                total += 1
    return total


def main():
    parser = argparse.ArgumentParser(
        description="Run fixed-scale calibration sweep and produce comparison table + merged shapefiles."
    )
    parser.add_argument("--python", default=sys.executable, help="Python interpreter to run subprocess tools")
    parser.add_argument("--img-dir", default="calib_imgs", help="Directory with calibration GeoTIFFs")
    parser.add_argument("--out-root", default="calibration_runs", help="Output root directory for sweep artifacts")
    parser.add_argument(
        "--fixed-scale-max-values",
        nargs="+",
        type=float,
        default=[12520, 10000, 8000, 6000, 5000],
        help="List of fixed-scale max values to test",
    )
    parser.add_argument("--fixed-scale-min", type=float, default=0.0, help="Fixed-scale minimum value")
    parser.add_argument("--score-thr", nargs="+", type=float, default=[0.85], help="Output score thresholds")
    parser.add_argument("--batch-size", type=int, default=99999, help="Batch size passed to batch_detect_africa.py")
    parser.add_argument("--force", action="store_true", help="Re-run settings even if outputs already exist")
    args = parser.parse_args()

    if not os.path.isdir(args.img_dir):
        raise SystemExit(f"Input directory not found: {args.img_dir}")
    if args.fixed_scale_min >= min(args.fixed_scale_max_values):
        raise SystemExit("--fixed-scale-min must be smaller than all fixed-scale-max values")
    batch_script = os.path.abspath("batch_detect_africa.py")
    summarize_script = os.path.abspath("tools/qa/summarize_mask_detections.py")
    merge_script = os.path.abspath("tools/qa/merge_mask_tifs_to_shapefile.py")

    ensure_dir(args.out_root)
    comparison_rows = []
    thresholds = [float(t) for t in args.score_thr]

    log(f"Starting calibration sweep on {args.img_dir}")
    log(f"Scale max values: {args.fixed_scale_max_values}")
    log(f"Score thresholds: {thresholds}")

    for fx_max in args.fixed_scale_max_values:
        setting = f"fx{scale_tag(args.fixed_scale_min)}_{scale_tag(fx_max)}"
        setting_dir = os.path.join(args.out_root, setting)
        ensure_dir(setting_dir)

        result_dir = os.path.join(setting_dir, "result")
        preprocess_cache = os.path.join(setting_dir, "preprocess_cache")
        preprocess_manifest = os.path.join(setting_dir, "preprocess_manifest.json")
        progress_file = os.path.join(setting_dir, "progress.json")
        run_log = os.path.join(setting_dir, "batch_output.log")
        summary_csv = os.path.join(setting_dir, "detection_counts_summary.csv")
        summary_json = os.path.join(setting_dir, "detection_counts_summary.json")

        row = {
            "setting": setting,
            "fixed_scale_min": float(args.fixed_scale_min),
            "fixed_scale_max": float(fx_max),
            "status": "not_run",
            "completed_tiles": 0,
            "failed_tiles": 0,
            "no_detection_tiles": 0,
            "mask_files_total": 0,
            "rows_written": 0,
            "result_dir": os.path.abspath(result_dir),
        }

        batch_done = os.path.exists(progress_file) and os.path.exists(result_dir)
        if batch_done and not args.force:
            log(f"[{setting}] Reusing existing outputs")
            rc = 0
        else:
            cmd = [
                args.python,
                batch_script,
                "--auto",
                "--img_dir",
                args.img_dir,
                "--batch-size",
                str(max(1, int(args.batch_size))),
                "--ignore-progress",
                "--preprocess-mode",
                "fixed",
                "--fixed-scale-min",
                str(args.fixed_scale_min),
                "--fixed-scale-max",
                str(fx_max),
                "--preprocess-cache-dir",
                preprocess_cache,
                "--preprocess-manifest",
                preprocess_manifest,
                "--progress-file",
                progress_file,
                "--seg-res-path",
                result_dir,
                "--workdir",
                os.path.join(setting_dir, "temp"),
                "--allow-partial",
                "--score-thr",
            ] + [str(t) for t in thresholds]

            cmd.append("--skip-arid-filter")

            rc = run_cmd(cmd, run_log)

        row["status"] = "ok" if rc == 0 else "batch_failed"

        progress = load_json(progress_file, {})
        row["completed_tiles"] = len(progress.get("completed_tiles", []))
        row["failed_tiles"] = len(progress.get("failed_tiles", []))
        row["no_detection_tiles"] = len(progress.get("no_detection_tiles", []))

        mask_file_count = count_union_mask_tifs(result_dir)
        row["mask_files_total"] = int(mask_file_count)

        if os.path.isdir(result_dir) and mask_file_count > 0:
            sum_cmd = [
                args.python,
                summarize_script,
                "--result-dir",
                result_dir,
                "--out-csv",
                summary_csv,
                "--out-json",
                summary_json,
            ]
            sum_log = os.path.join(setting_dir, "summarize_output.log")
            sum_rc = run_cmd(sum_cmd, sum_log)
            if sum_rc != 0 and row["status"] == "ok":
                row["status"] = "summary_failed"

            thr_map = threshold_summary_map(summary_json)
            sum_data = load_json(summary_json, {})
            row["rows_written"] = int(sum_data.get("rows_written", 0))
            row["mask_files_total"] = int(sum_data.get("summary", {}).get("mask_files_total", 0))

            for thr in thresholds:
                thr_txt = threshold_text(thr)
                thr_key = threshold_tag(thr)
                thr_row = thr_map.get(thr_txt, {})
                row[f"components_total_thr_{thr_key}"] = int(thr_row.get("components_total", 0))
                row[f"tiles_with_masks_thr_{thr_key}"] = int(thr_row.get("tiles", 0))

                shp_path = os.path.join(setting_dir, f"merged_thr_{thr_key}.shp")
                merge_cmd = [
                    args.python,
                    merge_script,
                    "--result-dir",
                    result_dir,
                    "--threshold",
                    str(thr),
                    "--output-shp",
                    shp_path,
                ]
                merge_log = os.path.join(setting_dir, f"merge_thr_{thr_key}.log")
                merge_rc = run_cmd(merge_cmd, merge_log)
                row[f"merge_rc_thr_{thr_key}"] = int(merge_rc)
                row[f"shp_path_thr_{thr_key}"] = os.path.abspath(shp_path) if os.path.exists(shp_path) else ""
                row[f"shp_features_thr_{thr_key}"] = shp_feature_count(shp_path) if merge_rc == 0 else 0

                if merge_rc != 0 and row["status"] == "ok":
                    row["status"] = "merge_failed"
        else:
            row["rows_written"] = 0
            for thr in thresholds:
                thr_key = threshold_tag(thr)
                row[f"components_total_thr_{thr_key}"] = 0
                row[f"tiles_with_masks_thr_{thr_key}"] = 0
                row[f"merge_rc_thr_{thr_key}"] = 0
                row[f"shp_path_thr_{thr_key}"] = ""
                row[f"shp_features_thr_{thr_key}"] = 0
            if row["status"] == "ok":
                row["status"] = "ok_no_masks"

        comparison_rows.append(row)
        log(f"[{setting}] status={row['status']} completed={row['completed_tiles']} failed={row['failed_tiles']}")

    comparison_json = os.path.join(args.out_root, "calibration_comparison.json")
    existing = load_json(comparison_json, {})
    merged_rows = upsert_rows(existing.get("rows", []), comparison_rows)

    payload = {
        "generated_at": utc_now(),
        "img_dir": os.path.abspath(args.img_dir),
        "out_root": os.path.abspath(args.out_root),
        "score_thresholds": thresholds,
        "rows": merged_rows,
    }
    save_json(comparison_json, payload)

    fieldnames = []
    for r in merged_rows:
        for key in r.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    comparison_csv = os.path.join(args.out_root, "calibration_comparison.csv")
    with open(comparison_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged_rows)

    log(f"Wrote comparison JSON: {comparison_json}")
    log(f"Wrote comparison CSV: {comparison_csv}")
    log("Calibration sweep complete.")


if __name__ == "__main__":
    main()
