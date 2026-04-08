"""Train CPI candidate classifier."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cpis.common.file_utils import ensure_dir, save_json
from cpis.common.logging_utils import build_logger
from cpis.common.time_utils import utc_now_iso


DEFAULT_FEATURE_COLUMNS = [
    "geom_score",
    "ndvi_amp",
    "ring_contrast",
    "texture_score",
    "radius_m",
    "radius_px",
    "pixel_size_m",
]


def _load_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Training table not found: {path}")
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _select_features(df: pd.DataFrame, label_col: str, explicit: list[str]) -> list[str]:
    if explicit:
        missing = [c for c in explicit if c not in df.columns]
        if missing:
            raise RuntimeError(f"Requested feature columns missing from table: {missing}")
        return explicit

    candidates = [c for c in DEFAULT_FEATURE_COLUMNS if c in df.columns]
    if candidates:
        return candidates

    fallback = [
        c
        for c in df.columns
        if c != label_col and pd.api.types.is_numeric_dtype(df[c]) and c not in {"year"}
    ]
    if not fallback:
        raise RuntimeError("No numeric features found in training table.")
    return fallback


def _pick_model(algorithm: str):
    algo = algorithm.lower()
    if algo in {"auto", "xgboost"}:
        try:
            from xgboost import XGBClassifier

            return "xgboost", XGBClassifier(
                n_estimators=300,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.9,
                colsample_bytree=0.9,
                objective="binary:logistic",
                eval_metric="logloss",
                n_jobs=-1,
                random_state=42,
            )
        except Exception:
            if algo == "xgboost":
                raise

    if algo in {"auto", "lightgbm"}:
        try:
            from lightgbm import LGBMClassifier

            return "lightgbm", LGBMClassifier(
                n_estimators=400,
                learning_rate=0.05,
                num_leaves=63,
                subsample=0.9,
                colsample_bytree=0.9,
                random_state=42,
            )
        except Exception:
            if algo == "lightgbm":
                raise

    try:
        from sklearn.ensemble import HistGradientBoostingClassifier

        return "sklearn_hgbt", HistGradientBoostingClassifier(
            max_depth=8,
            learning_rate=0.05,
            max_iter=350,
            random_state=42,
        )
    except Exception as exc:
        raise RuntimeError(
            "Could not load xgboost/lightgbm/sklearn classifier dependencies. "
            "Install dependencies from environment.yml"
        ) from exc


def _save_model(model, model_type: str, out_model: Path) -> str:
    ensure_dir(out_model.parent)
    if model_type == "xgboost":
        # Keep plan-aligned JSON artifact for v1 default.
        if out_model.suffix.lower() != ".json":
            out_model = out_model.with_suffix(".json")
        model.save_model(str(out_model))
        return str(out_model.resolve())

    try:
        import joblib
    except ModuleNotFoundError as exc:
        raise RuntimeError("Missing dependency 'joblib' for model persistence.") from exc

    if out_model.suffix.lower() != ".joblib":
        out_model = out_model.with_suffix(".joblib")
    joblib.dump(model, out_model)
    return str(out_model.resolve())


def _downsample_train_negatives(
    train_df: pd.DataFrame,
    label_col: str,
    ratio: float,
    seed: int,
    min_negatives: int,
    log,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if ratio <= 0:
        return train_df, {"enabled": False}

    if label_col not in train_df.columns:
        return train_df, {"enabled": True, "applied": False, "reason": f"missing_label_col:{label_col}"}

    pos = train_df[train_df[label_col] == 1]
    neg = train_df[train_df[label_col] == 0]
    if pos.empty or neg.empty:
        return train_df, {
            "enabled": True,
            "applied": False,
            "reason": "need_both_classes",
            "pos": int(len(pos)),
            "neg": int(len(neg)),
        }

    target_neg = int(round(float(ratio) * len(pos)))
    target_neg = max(int(min_negatives), target_neg)
    target_neg = min(target_neg, len(neg))
    if target_neg >= len(neg):
        return train_df, {
            "enabled": True,
            "applied": False,
            "reason": "no_reduction_needed",
            "pos": int(len(pos)),
            "neg_before": int(len(neg)),
            "neg_after": int(len(neg)),
        }

    neg_keep = neg.sample(n=target_neg, random_state=int(seed))
    out = pd.concat([pos, neg_keep], ignore_index=True)
    out = out.sample(frac=1.0, random_state=int(seed)).reset_index(drop=True)
    log(
        f"Applied negative downsampling: pos={len(pos)} "
        f"neg_before={len(neg)} neg_after={len(neg_keep)} ratio={ratio}"
    )
    return out, {
        "enabled": True,
        "applied": True,
        "ratio": float(ratio),
        "pos": int(len(pos)),
        "neg_before": int(len(neg)),
        "neg_after": int(len(neg_keep)),
        "min_negatives": int(min_negatives),
    }


def run_train(args: argparse.Namespace) -> int:
    log = build_logger(args.log_file if args.log_file else "")
    train_table = Path(args.train_table)
    out_model = Path(args.out_model)
    feature_schema_path = Path(args.feature_schema)
    report_path = Path(args.report)
    meta_path = Path(args.model_meta)

    log(f"Loading table: {train_table}")
    df = _load_table(train_table)
    label_col = args.label_column
    if label_col not in df.columns:
        raise RuntimeError(f"Label column '{label_col}' not in training table.")

    feature_cols = _select_features(df, label_col=label_col, explicit=args.feature_columns)
    log(f"Using {len(feature_cols)} feature columns: {feature_cols}")

    weight_col = str(args.sample_weight_column).strip()
    extra_cols: list[str] = []
    if weight_col:
        if weight_col not in df.columns:
            raise RuntimeError(f"Sample-weight column '{weight_col}' not in training table.")
        extra_cols.append(weight_col)

    clean = df[[*feature_cols, label_col, *extra_cols]].dropna(subset=feature_cols + [label_col]).copy()
    clean = clean[(clean[label_col] == 0) | (clean[label_col] == 1)].copy()
    if clean.empty:
        raise RuntimeError("No valid rows after filtering NaNs/labels.")

    from sklearn.model_selection import train_test_split
    from sklearn.metrics import average_precision_score, precision_recall_curve, f1_score

    all_idx = np.arange(len(clean))
    labels = clean[label_col].astype(int).values
    idx_train, idx_val = train_test_split(
        all_idx,
        test_size=float(args.test_size),
        random_state=int(args.random_state),
        stratify=labels if len(np.unique(labels)) > 1 else None,
    )
    train_df = clean.iloc[idx_train].copy()
    val_df = clean.iloc[idx_val].copy()

    train_pos_before = int((train_df[label_col] == 1).sum())
    train_neg_before = int((train_df[label_col] == 0).sum())
    val_pos = int((val_df[label_col] == 1).sum())
    val_neg = int((val_df[label_col] == 0).sum())

    train_df, downsample_info = _downsample_train_negatives(
        train_df=train_df,
        label_col=label_col,
        ratio=float(args.negative_downsample_ratio),
        seed=int(args.downsample_seed),
        min_negatives=int(args.min_negatives),
        log=log,
    )

    X_train = train_df[feature_cols].astype(float).values
    y_train = train_df[label_col].astype(int).values
    X_val = val_df[feature_cols].astype(float).values
    y_val = val_df[label_col].astype(int).values

    sample_weight = None
    if weight_col:
        sample_weight = (
            pd.to_numeric(train_df[weight_col], errors="coerce")
            .fillna(1.0)
            .clip(lower=0.0)
            .astype(float)
            .values
        )
        log(
            f"Using sample weights from '{weight_col}': "
            f"min={float(np.min(sample_weight)):.3f} max={float(np.max(sample_weight)):.3f}"
        )

    model_type, model = _pick_model(args.algorithm)
    log(f"Training model: {model_type}")
    fit_kwargs: dict[str, Any] = {}
    if sample_weight is not None:
        fit_kwargs["sample_weight"] = sample_weight
    try:
        model.fit(X_train, y_train, **fit_kwargs)
    except TypeError:
        if fit_kwargs:
            log("[warn] model.fit does not support sample_weight for this backend; continuing without it.")
        model.fit(X_train, y_train)
    if hasattr(model, "predict_proba"):
        y_score = model.predict_proba(X_val)[:, 1]
    else:
        raw = model.decision_function(X_val)
        y_score = (raw - raw.min()) / max(1e-6, raw.max() - raw.min())

    precision, recall, thresholds = precision_recall_curve(y_val, y_score)
    ap = float(average_precision_score(y_val, y_score))

    # Threshold policies.
    best_f1 = -1.0
    best_thr_bal = 0.5
    best_thr_prec = 0.5
    best_thr_rec = 0.5
    best_prec_rec = -1.0
    best_rec_prec = -1.0
    thr_grid = thresholds if len(thresholds) > 0 else np.array([0.5], dtype=float)

    for thr in thr_grid:
        y_hat = (y_score >= thr).astype(int)
        f1 = float(f1_score(y_val, y_hat, zero_division=0))
        if f1 > best_f1:
            best_f1 = f1
            best_thr_bal = float(thr)

        tp = int(((y_hat == 1) & (y_val == 1)).sum())
        fp = int(((y_hat == 1) & (y_val == 0)).sum())
        fn = int(((y_hat == 0) & (y_val == 1)).sum())
        prec = float(tp / max(1, tp + fp))
        rec = float(tp / max(1, tp + fn))
        if prec >= 0.90 and rec > best_prec_rec:
            best_prec_rec = rec
            best_thr_prec = float(thr)
        if rec >= 0.80 and prec > best_rec_prec:
            best_rec_prec = prec
            best_thr_rec = float(thr)

    model_path = _save_model(model, model_type=model_type, out_model=out_model)
    schema_payload = {
        "generated_at": utc_now_iso(),
        "feature_columns": feature_cols,
        "label_column": label_col,
        "model_type": model_type,
    }
    save_json(feature_schema_path, schema_payload)

    report_payload: dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "model_type": model_type,
        "train_rows": int(len(X_train)),
        "val_rows": int(len(X_val)),
        "average_precision": ap,
        "class_balance": {
            "train_pos_before_downsample": train_pos_before,
            "train_neg_before_downsample": train_neg_before,
            "train_pos_after_downsample": int((y_train == 1).sum()),
            "train_neg_after_downsample": int((y_train == 0).sum()),
            "val_pos": val_pos,
            "val_neg": val_neg,
        },
        "downsample": downsample_info,
        "sample_weight_column": weight_col,
        "threshold_policies": {
            "precision_first": best_thr_prec,
            "balanced": best_thr_bal,
            "recall_first": best_thr_rec,
        },
    }
    save_json(report_path, report_payload)

    meta_payload = {
        "generated_at": utc_now_iso(),
        "model_path": model_path,
        "model_type": model_type,
        "feature_schema_path": str(feature_schema_path.resolve()),
        "report_path": str(report_path.resolve()),
    }
    save_json(meta_path, meta_payload)

    log(f"Model saved: {model_path}")
    log(f"Feature schema: {feature_schema_path}")
    log(f"Calibration report: {report_path}")
    log(f"Model meta: {meta_path}")
    return 0


def build_parser(subparsers) -> None:
    p = subparsers.add_parser("train", help="Train candidate classifier model")
    p.add_argument("--train-table", required=True, help="Training table path (.parquet or .csv)")
    p.add_argument("--label-column", default="label", help="Binary label column")
    p.add_argument("--feature-columns", nargs="*", default=[], help="Explicit feature columns")
    p.add_argument("--algorithm", default="auto", help="auto|xgboost|lightgbm|sklearn")
    p.add_argument("--test-size", type=float, default=0.2, help="Validation split fraction")
    p.add_argument("--random-state", type=int, default=42, help="Random seed")
    p.add_argument("--sample-weight-column", default="", help="Optional sample-weight column")
    p.add_argument(
        "--negative-downsample-ratio",
        type=float,
        default=0.0,
        help="If >0, cap training negatives to ratio * positives (applies to train split only)",
    )
    p.add_argument("--downsample-seed", type=int, default=42, help="Random seed for negative downsampling")
    p.add_argument("--min-negatives", type=int, default=0, help="Minimum negatives kept when downsampling")
    p.add_argument("--out-model", default="models/cpi_candidate_classifier_v1.json", help="Model output path")
    p.add_argument("--feature-schema", default="models/feature_schema_v1.json", help="Feature schema output")
    p.add_argument("--report", default="models/calibration_report_v1.json", help="Training/calibration report output")
    p.add_argument("--model-meta", default="models/cpi_candidate_classifier_v1.meta.json", help="Model metadata JSON")
    p.add_argument("--log-file", default="", help="Optional log file path")
    p.set_defaults(func=run_train)
