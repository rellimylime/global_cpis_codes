import argparse
import csv
import json
import os
import re
from datetime import datetime

import numpy as np

try:
    import cv2
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency 'cv2'. Run with the CPI detection environment.") from exc

try:
    from osgeo import gdal
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency 'osgeo' (GDAL). Run with the CPI detection environment.") from exc


MASK_RE = re.compile(r"^(?P<tile>.+)union_segm_(?P<thr>[^\\/]+)\.tif$", re.IGNORECASE)


def utc_now_iso():
    return datetime.utcnow().isoformat() + "Z"


def discover_mask_files(result_dir):
    paths = []
    for root, _, files in os.walk(result_dir):
        for fn in files:
            if fn.lower().endswith(".tif") and "union_segm_" in fn.lower():
                paths.append(os.path.join(root, fn))
    return sorted(paths)


def parse_mask_name(path):
    name = os.path.basename(path)
    m = MASK_RE.match(name)
    if not m:
        return None, None
    return m.group("tile"), m.group("thr")


def component_count(binary_mask, connectivity, min_pixels):
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(binary_mask, connectivity=connectivity)
    if num_labels <= 1:
        return 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    if min_pixels <= 1:
        return int(num_labels - 1)
    return int(np.sum(areas >= int(min_pixels)))


def threshold_sort_key(thr_text):
    try:
        return (0, float(thr_text))
    except Exception:
        return (1, thr_text)


def summarize(rows):
    by_threshold = {}
    tiles = set()
    for row in rows:
        thr = row["threshold"]
        tiles.add(row["tile"])
        if thr not in by_threshold:
            by_threshold[thr] = {
                "tiles": 0,
                "components_total": 0,
                "positive_pixels_total": 0,
            }
        by_threshold[thr]["tiles"] += 1
        by_threshold[thr]["components_total"] += int(row["component_count"])
        by_threshold[thr]["positive_pixels_total"] += int(row["positive_pixels"])

    ordered_thresholds = [
        {"threshold": thr, **by_threshold[thr]}
        for thr in sorted(by_threshold.keys(), key=threshold_sort_key)
    ]

    return {
        "tiles_total": len(tiles),
        "mask_files_total": len(rows),
        "thresholds": ordered_thresholds,
    }


def main():
    parser = argparse.ArgumentParser(description="Summarize detection mask TIFFs into CSV/JSON QA reports")
    parser.add_argument("--result-dir", default="result_africa", help="Directory containing detection outputs")
    parser.add_argument("--out-csv", default="", help="Output CSV path (default: <result-dir>/detection_counts_summary.csv)")
    parser.add_argument("--out-json", default="", help="Output JSON path (default: <result-dir>/detection_counts_summary.json)")
    parser.add_argument("--connectivity", type=int, choices=[4, 8], default=8, help="Connected-components connectivity")
    parser.add_argument("--min-pixels", type=int, default=1, help="Minimum component pixel size to count")
    parser.add_argument("--progress-every", type=int, default=25, help="Print progress every N mask files")
    parser.add_argument("--verbose", action="store_true", help="Print every processed mask file")
    args = parser.parse_args()

    if not os.path.isdir(args.result_dir):
        raise SystemExit(f"Result directory not found: {args.result_dir}")

    out_csv = args.out_csv or os.path.join(args.result_dir, "detection_counts_summary.csv")
    out_json = args.out_json or os.path.join(args.result_dir, "detection_counts_summary.json")
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(out_json) or ".", exist_ok=True)

    mask_paths = discover_mask_files(args.result_dir)
    if not mask_paths:
        raise SystemExit(f"No union mask TIFF files found under: {args.result_dir}")

    print(f"[{utc_now_iso()}] Scanning {len(mask_paths)} mask files in {args.result_dir}")

    rows = []
    skipped = []
    total = len(mask_paths)

    for idx, mask_path in enumerate(mask_paths, 1):
        tile_name, thr_text = parse_mask_name(mask_path)
        if tile_name is None:
            skipped.append(mask_path)
            continue

        ds = gdal.Open(mask_path)
        if ds is None:
            skipped.append(mask_path)
            continue
        arr = ds.ReadAsArray()
        ds = None
        if arr is None:
            skipped.append(mask_path)
            continue
        if arr.ndim > 2:
            arr = arr[0]

        binary = (arr > 0).astype(np.uint8)
        positive_pixels = int(np.count_nonzero(binary))
        components = component_count(binary, args.connectivity, args.min_pixels)
        height, width = int(binary.shape[0]), int(binary.shape[1])
        total_pixels = int(height * width)

        row = {
            "tile": tile_name,
            "threshold": str(thr_text),
            "component_count": int(components),
            "positive_pixels": positive_pixels,
            "coverage_fraction": float(positive_pixels / total_pixels) if total_pixels > 0 else 0.0,
            "width": width,
            "height": height,
            "mask_path": os.path.abspath(mask_path),
        }
        rows.append(row)

        if args.verbose:
            print(f"  [{idx}/{total}] {tile_name} thr={thr_text} components={components} pixels={positive_pixels}")
        elif args.progress_every > 0 and ((idx % args.progress_every == 0) or (idx == total)):
            print(f"[{utc_now_iso()}] Processed {idx}/{total} masks")

    rows.sort(key=lambda r: (r["tile"], threshold_sort_key(r["threshold"])))

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "tile",
                "threshold",
                "component_count",
                "positive_pixels",
                "coverage_fraction",
                "width",
                "height",
                "mask_path",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "generated_at": utc_now_iso(),
        "result_dir": os.path.abspath(args.result_dir),
        "out_csv": os.path.abspath(out_csv),
        "out_json": os.path.abspath(out_json),
        "connectivity": args.connectivity,
        "min_pixels": args.min_pixels,
        "rows_written": len(rows),
        "skipped_files": len(skipped),
        "summary": summarize(rows),
    }
    if skipped:
        summary["skipped_paths"] = [os.path.abspath(p) for p in skipped]

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"[{utc_now_iso()}] Wrote CSV: {out_csv}")
    print(f"[{utc_now_iso()}] Wrote JSON: {out_json}")
    print(f"[{utc_now_iso()}] Rows: {len(rows)}, skipped: {len(skipped)}")


if __name__ == "__main__":
    main()
