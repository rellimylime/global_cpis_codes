"""Prepare V6 training labels and updated gold eval holdout.

Splits 2015_gold_val_v1.gpkg into:
  - tiles 000022 + 000026  → added to training (407 manual positives)
  - tiles 000015 + 000033  → kept as gold eval holdout (1,282 manual positives)

Merges those 407 new training polygons with 2015_train_augmented_v1.gpkg to produce
2015_train_v6_merged.gpkg (used to build the V6 COCO training dataset).

Outputs (all written to manual_labels/):
  2015_train_v6_merged.gpkg       -- merged training labels (~6,424 polygons)
  2015_gold_val_v2_holdout.gpkg   -- holdout eval labels (1,282 polygons, tiles 000015+000033)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import geopandas as gpd
import pandas as pd

MANUAL_LABELS_DIR = ROOT / "runs/new_method/rse2023_2015_v1/manual_labels"

GOLD_VAL_PATH = MANUAL_LABELS_DIR / "2015_gold_val_v1.gpkg"
AUG_TRAIN_PATH = MANUAL_LABELS_DIR / "2015_train_augmented_v1.gpkg"

OUT_TRAIN = MANUAL_LABELS_DIR / "2015_train_v6_merged.gpkg"
OUT_HOLDOUT = MANUAL_LABELS_DIR / "2015_gold_val_v2_holdout.gpkg"

# Gold val tiles to move into training
TRAIN_TILES = {"cpis_landsat_2015_tile_000022", "cpis_landsat_2015_tile_000026"}
# Gold val tiles to keep as eval holdout
HOLDOUT_TILES = {"cpis_landsat_2015_tile_000015", "cpis_landsat_2015_tile_000033"}


def main() -> int:
    gv = gpd.read_file(GOLD_VAL_PATH)
    aug = gpd.read_file(AUG_TRAIN_PATH)

    print(f"Loaded gold_val: {len(gv)} polygons across tiles: {sorted(gv['source_name'].unique())}")
    print(f"Loaded aug_train: {len(aug)} polygons")

    # --- holdout: tiles 000015 + 000033 only ---
    holdout = gv[gv["source_name"].isin(HOLDOUT_TILES)].copy()
    holdout = holdout.reset_index(drop=True)
    holdout.to_file(OUT_HOLDOUT, driver="GPKG")
    print(f"\nWrote holdout ({len(holdout)} polygons) → {OUT_HOLDOUT}")
    print("  Holdout breakdown:")
    for src, cnt in holdout["source_name"].value_counts().items():
        print(f"    {src}: {cnt}")

    # --- new training polygons: tiles 000022 + 000026 ---
    new_train = gv[gv["source_name"].isin(TRAIN_TILES)].copy()
    new_train = new_train[["label_id", "source_name", "label_set", "status",
                            "partial", "notes", "geometry"]].copy()
    # Mark as training so build_paper_dataset.py treats them identically
    new_train["label_set"] = "train"
    print(f"\nNew training polygons from gold val tiles: {len(new_train)}")
    for src, cnt in new_train["source_name"].value_counts().items():
        print(f"    {src}: {cnt}")

    # --- merge with existing aug training labels ---
    # Keep all aug columns; fill missing ones in new_train with NaN
    merged = pd.concat([aug, new_train], ignore_index=True)
    merged_gdf = gpd.GeoDataFrame(merged, geometry="geometry", crs=aug.crs)
    merged_gdf.to_file(OUT_TRAIN, driver="GPKG")
    print(f"\nWrote merged training labels ({len(merged_gdf)} polygons) → {OUT_TRAIN}")
    print("  source breakdown (manual tiles only):")
    manual_sources = sorted(TRAIN_TILES | {"cpis_landsat_2015_tile_000023",
                                            "cpis_landsat_2015_tile_000024",
                                            "cpis_landsat_2015_tile_000035"})
    for src in manual_sources:
        cnt = (merged_gdf["source_name"] == src).sum()
        if cnt:
            print(f"    {src}: {cnt}")

    total_manual = len(new_train) + len(aug[aug["label_set"] == "train"])
    print(f"\nTotal manual positives in training: {total_manual}")
    print(f"Total training labels (weak + manual): {len(merged_gdf)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
