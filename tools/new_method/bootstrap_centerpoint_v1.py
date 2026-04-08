"""Bootstrap centerpoint_v1 training artifacts from manual point labels.

This script wraps existing CLI commands to:
1) Transfer positive point labels to nearest candidates
2) Optionally transfer negative point labels
3) Build a training table
4) Optionally train a model
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_cmd(cmd: list[str], log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(f"\n[{utc_now_iso()}] RUN: {' '.join(cmd)}\n")
        f.flush()
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd)}")


def point_label_counts(points_path: Path) -> dict[str, int]:
    gdf = gpd.read_file(points_path)
    if gdf.empty:
        return {"rows": 0, "pos": 0, "neg": 0, "other": 0, "has_label": 0}

    if "label" not in gdf.columns:
        return {"rows": int(len(gdf)), "pos": int(len(gdf)), "neg": 0, "other": 0, "has_label": 0}

    label = pd.to_numeric(gdf["label"], errors="coerce")
    pos = int((label == 1).sum())
    neg = int((label == 0).sum())
    other = int((~label.isin([0, 1])).sum())
    return {"rows": int(len(gdf)), "pos": pos, "neg": neg, "other": other, "has_label": 1}


def resolve_candidates_path(candidates: Path) -> Path:
    if candidates.suffix.lower() != ".parquet":
        return candidates
    try:
        # Fast sanity check for parquet support in this environment.
        pd.read_parquet(candidates, columns=[])
        return candidates
    except Exception:
        alt = candidates.with_suffix(".csv")
        if alt.exists():
            return alt
        raise


def labeled_counts(vector_path: Path) -> dict[str, int]:
    if not vector_path.exists():
        return {"rows": 0, "label_1": 0, "label_0": 0, "label_other": 0}
    gdf = gpd.read_file(vector_path)
    if gdf.empty or "label" not in gdf.columns:
        return {"rows": int(len(gdf)), "label_1": 0, "label_0": 0, "label_other": int(len(gdf))}
    label = pd.to_numeric(gdf["label"], errors="coerce")
    l1 = int((label == 1).sum())
    l0 = int((label == 0).sum())
    other = int((~label.isin([0, 1])).sum())
    return {"rows": int(len(gdf)), "label_1": l1, "label_0": l0, "label_other": other}


def main() -> None:
    p = argparse.ArgumentParser(description="Bootstrap centerpoint_v1 from manual point labels.")
    p.add_argument("--candidates", required=True, help="Candidate table path (.parquet/.csv/.gpkg/.shp)")
    p.add_argument("--manual-points", required=True, help="Manual point labels path with optional label field")
    p.add_argument("--out-root", default="runs/new_method/centerpoint_v1/bootstrap", help="Output root")
    p.add_argument("--max-distance-m", type=float, default=600.0, help="Max anchor->candidate transfer distance")
    p.add_argument("--allow-cross-tile", action="store_true", help="Allow nearest matching across tile boundaries")
    p.add_argument("--edge-policy", default="ignore", choices=["ignore", "positive", "negative", "drop"])
    p.add_argument("--train", action="store_true", help="Train model after train-table build")
    p.add_argument("--negative-downsample-ratio", type=float, default=4.0, help="Train negatives cap ratio")
    p.add_argument("--min-negatives", type=int, default=200, help="Minimum negatives kept after downsampling")
    p.add_argument("--python", default=sys.executable, help="Python interpreter for subprocess calls")
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    cpis_entry = repo_root / "cpis.py"

    candidates = resolve_candidates_path(Path(args.candidates))
    manual_points = Path(args.manual_points)
    out_root = Path(args.out_root)
    labels_dir = out_root / "labels"
    training_dir = out_root / "training"
    models_dir = out_root / "models"
    logs_dir = out_root / "logs"
    for d in [labels_dir, training_dir, models_dir, logs_dir]:
        d.mkdir(parents=True, exist_ok=True)

    if not candidates.exists():
        raise FileNotFoundError(f"Candidates not found: {candidates}")
    if not manual_points.exists():
        raise FileNotFoundError(f"Manual points not found: {manual_points}")

    counts = point_label_counts(manual_points)
    if counts["rows"] == 0:
        raise RuntimeError("Manual points layer is empty.")
    if counts["pos"] <= 0:
        raise RuntimeError("No positive points found (label=1).")

    log_file = logs_dir / "bootstrap.log"
    label_pos = labels_dir / "manual_points_pos.gpkg"
    label_posneg = labels_dir / "manual_points_posneg.gpkg"
    train_table = training_dir / "centerpoint_v1_train.csv"
    train_summary = training_dir / "centerpoint_v1_train.summary.json"

    base_cmd = [args.python, str(cpis_entry)]
    cross_tile_flag = ["--allow-cross-tile"] if args.allow_cross_tile else []

    cmd_pos = base_cmd + [
        "qa",
        "transfer-anchor-labels",
        "--candidates",
        str(candidates),
        "--anchors",
        str(manual_points),
        "--out",
        str(label_pos),
        "--anchor-label-column",
        "label",
        "--anchor-positive-value",
        "1",
        "--positive-label",
        "1",
        "--max-distance-m",
        str(args.max_distance_m),
        "--only-unlabeled",
        "--set-review-status",
        "manual_pos",
    ] + cross_tile_flag
    run_cmd(cmd_pos, log_file)
    pos_counts = labeled_counts(label_pos)
    if pos_counts["label_1"] <= 0:
        summary_path = out_root / "bootstrap_summary.json"
        summary = {
            "generated_at": utc_now_iso(),
            "status": "no_candidate_matches",
            "reason": "No candidate rows were matched/labeled as positive.",
            "inputs": {
                "candidates": str(candidates.resolve()),
                "manual_points": str(manual_points.resolve()),
                "manual_point_counts": counts,
            },
            "outputs": {
                "labels_positive": str(label_pos.resolve()),
                "log_file": str(log_file.resolve()),
            },
            "advice": (
                "Use candidate features from the same geography/tile as manual points, "
                "or increase --max-distance-m if appropriate."
            ),
        }
        with summary_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        raise RuntimeError(
            "No positive candidate matches were transferred. "
            f"See summary: {summary_path}"
        )

    label_input_for_train = label_pos
    if counts["neg"] > 0 and counts["has_label"] == 1:
        cmd_neg = base_cmd + [
            "qa",
            "transfer-anchor-labels",
            "--candidates",
            str(label_pos),
            "--anchors",
            str(manual_points),
            "--out",
            str(label_posneg),
            "--anchor-label-column",
            "label",
            "--anchor-positive-value",
            "0",
            "--positive-label",
            "0",
            "--max-distance-m",
            str(args.max_distance_m),
            "--only-unlabeled",
            "--set-review-status",
            "manual_neg",
        ] + cross_tile_flag
        run_cmd(cmd_neg, log_file)
        label_input_for_train = label_posneg

    cmd_train_table = base_cmd + [
        "qa",
        "build-train-table",
        "--labeled-input",
        str(label_input_for_train),
        "--label-field",
        "label",
        "--out-table",
        str(train_table),
        "--deduplicate",
        "--edge-policy",
        str(args.edge_policy),
    ]
    run_cmd(cmd_train_table, log_file)
    train_counts = {"label_1": 0, "label_0": 0}
    if train_table.exists():
        train_df = pd.read_csv(train_table)
        if "label" in train_df.columns:
            train_label = pd.to_numeric(train_df["label"], errors="coerce")
            train_counts["label_1"] = int((train_label == 1).sum())
            train_counts["label_0"] = int((train_label == 0).sum())

    model_meta = ""
    model_report = ""
    model_artifact = ""
    if args.train:
        if train_counts["label_1"] <= 0 or train_counts["label_0"] <= 0:
            raise RuntimeError(
                "Training requested but train table is not binary-balanced enough "
                f"(label_1={train_counts['label_1']}, label_0={train_counts['label_0']})."
            )
        model_artifact_path = models_dir / "centerpoint_v1_model.json"
        feature_schema_path = models_dir / "centerpoint_v1_feature_schema.json"
        report_path = models_dir / "centerpoint_v1_calibration_report.json"
        meta_path = models_dir / "centerpoint_v1_model.meta.json"
        cmd_train_model = base_cmd + [
            "model",
            "train",
            "--train-table",
            str(train_table),
            "--negative-downsample-ratio",
            str(args.negative_downsample_ratio),
            "--min-negatives",
            str(args.min_negatives),
            "--out-model",
            str(model_artifact_path),
            "--feature-schema",
            str(feature_schema_path),
            "--report",
            str(report_path),
            "--model-meta",
            str(meta_path),
        ]
        run_cmd(cmd_train_model, log_file)
        model_artifact = str(model_artifact_path.resolve())
        model_report = str(report_path.resolve())
        model_meta = str(meta_path.resolve())

    summary = {
        "generated_at": utc_now_iso(),
        "repo_root": str(repo_root.resolve()),
        "inputs": {
            "candidates": str(candidates.resolve()),
            "manual_points": str(manual_points.resolve()),
            "manual_point_counts": counts,
        },
        "outputs": {
            "labels_positive": str(label_pos.resolve()),
            "labels_posneg": str(label_posneg.resolve()) if label_posneg.exists() else "",
            "train_table": str(train_table.resolve()),
            "train_table_summary": str(train_summary.resolve()) if train_summary.exists() else "",
            "model_artifact": model_artifact,
            "model_report": model_report,
            "model_meta": model_meta,
            "log_file": str(log_file.resolve()),
        },
        "settings": {
            "max_distance_m": float(args.max_distance_m),
            "allow_cross_tile": bool(args.allow_cross_tile),
            "edge_policy": str(args.edge_policy),
            "trained_model": bool(args.train),
            "negative_downsample_ratio": float(args.negative_downsample_ratio),
            "min_negatives": int(args.min_negatives),
        },
        "train_table_label_counts": train_counts,
    }
    summary_path = out_root / "bootstrap_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote summary: {summary_path}")
    print(f"Train table: {train_table}")
    if model_meta:
        print(f"Model meta: {model_meta}")


if __name__ == "__main__":
    main()
