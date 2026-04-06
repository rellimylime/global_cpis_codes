# 2015 Manual Labeling Plan

Last updated: 2026-03-17

This plan is for manual 2015 labeling in QGIS for the paper-aligned
instance-segmentation workflow under `runs/new_method/rse2023_2015_v1/`.

## Short Answer

Use polygons.

- Points are useful for quick review or center-only bookkeeping, but they are
  not enough for the current training pipeline.
- Bounding boxes would work only for a different detector-style workflow and
  would throw away mask supervision.
- The current dataset builder expects polygon truth:
  - `tools/new_method/build_paper_dataset.py --labels ...`

## Why Polygons Are Needed

The current model is a one-category instance-segmentation model:

- `model/cascade_mask_rcnn_pointrend_cbam.py`
- `tools/new_method/train_paper_model.py`

The dataset builder converts polygon geometries into:

- mask segmentations
- bounding boxes derived from those polygons

So polygons give the model everything it needs. Points and boxes do not.

## Recommended Labeling Strategy

Do not try to manually label all 2015 tiles first.

Use three tiers:

1. Gold validation tiles

- Purpose:
  - create a trustworthy held-out set for model comparison
- Recommended size:
  - `10-15` parent source tiles to start
- Rule:
  - fully review and fully label every pivot in each selected tile
  - do not train on these tiles

2. Reviewed training tiles

- Purpose:
  - improve 2015 supervision where weak labels are least reliable
- Recommended size:
  - `20-30` parent source tiles to start
- Priority:
  - `change_zones`
  - tiles with obvious model misses
  - tiles with obvious false positives

3. Hard-negative review tiles

- Purpose:
  - reduce false positives
- Recommended size:
  - `10-15` tiles containing non-pivot circular features or repeated model
    mistakes
- Rule:
  - review the whole tile and confirm that suspicious non-pivots remain
    unlabeled

## Geometry Policy

Label one feature per pivot.

Use polygons that approximate the pivot footprint, not the center point and not
the bounding box.

Recommended drawing style:

- draw the irrigated circular field footprint
- do not worry about perfect sub-pixel precision
- use a reasonably smooth polygon
- a simple circle-like polygon is fine if it matches the visible footprint

For partial or ambiguous cases:

- If the pivot is clearly present and most of it is visible:
  - label it as a polygon
- If only a small fragment is visible and it is genuinely ambiguous:
  - do not force a positive polygon
  - mark it as ambiguous in notes or keep it out of the gold set
- If a pivot crosses a tile edge:
  - label the visible footprint you can defend from the imagery
  - do not guess large missing sections unless the full shape is obvious from
    adjacent loaded imagery

## What To Label in QGIS

Recommended initial package:

- one GeoPackage for gold validation:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_gold_val_v1.gpkg`
- one GeoPackage for reviewed training tiles:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_review_v1.gpkg`

Suggested polygon layer name:

- `pivots`

Suggested fields:

- `label_id`
- `source_name`
- `label_set`
- `status`
- `partial`
- `notes`

Suggested field meanings:

- `label_set`:
  - `val`
  - `train`
- `status`:
  - `confirmed`
  - `ambiguous`
  - `exclude`
- `partial`:
  - `0` or `1`

Important note:

- The current training code only needs polygon geometry.
- These fields are for review and bookkeeping, not because the builder requires
  them.

## What Not To Do

- Do not use points as the only manual label geometry for this workflow.
- Do not use bounding boxes unless we deliberately switch to a box-first
  detector.
- Do not mix gold validation tiles back into training.
- Do not only label easy stable pivots. The high-value tiles are often the hard
  2015 cases.

## Best First Labeling Pass

If time is limited, do this first:

1. fully label `10` gold validation tiles
2. fully review `10-15` hard training tiles from `change_zones`
3. fully review `5-10` tiles with obvious false positives

That will help more than labeling a much larger number of easy weak-label tiles.

## QGIS Workflow

Recommended QGIS setup:

1. Load the 2015 raw TIFFs for the selected source tiles.
2. Load these reference layers:
   - `runs/new_method/rse2023_2015_v1/anchor_truth/overlays/stable_pivots.gpkg`
   - `runs/new_method/rse2023_2015_v1/anchor_truth/overlays/change_zones.gpkg`
3. Load model predictions later for error review if needed.
4. Create a new polygon layer in a GeoPackage.
5. Digitize only defensible pivots.
6. Save often and keep validation tiles separate from training-review tiles.

## How Manual Labels Will Be Used

The intended use is:

- gold validation polygons:
  - fixed held-out evaluation set
- reviewed training polygons:
  - replace weak labels on reviewed source tiles only when the tile was
    exhaustively reviewed
  - if you only label obvious/high-confidence pivots and leave many true pivots
    unlabeled, do not use that tile as a full replacement layer yet
- hard-negative review tiles:
  - contribute negative chips because suspicious non-pivots remain unlabeled

Once you have the first manual layers, the next repo task should be:

- merge manual polygons with weak labels tile-by-tile
- prefer manual labels over weak labels on fully reviewed tiles
- rebuild the 2015 dataset from that merged layer

For gold validation, the next concrete step is:

```bash
python tools/new_method/prepare_gold_eval.py \
  --imagery-dir runs/new_method/rse2023_2015_v1/pilot_2015_ssa/raw \
  --labels runs/new_method/rse2023_2015_v1/manual_labels/2015_gold_val_v1.gpkg \
  --out-root runs/new_method/rse2023_2015_v1/gold_eval/2015_gold_val_v1 \
  --keep-empty
```

That builds a held-out COCO-style gold dataset from the manual polygons and the
matching source TIFFs.

Then evaluate a checkpoint on that gold dataset with:

```bash
sbatch --job-name=cpis_gold_eval \
  --export=CPIS_GOLD_DATASET_ROOT=runs/new_method/rse2023_2015_v1/gold_eval/2015_gold_val_v1/dataset,CPIS_GOLD_CONFIG=runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v3_from_2021_174031/resolved_config.py,CPIS_GOLD_CHECKPOINT=runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v3_from_2021_174031/best_segm_mAP_epoch_19.pth,CPIS_GOLD_OUT_TAG=2015_gold_val_eval \
  tools/new_method/run_gold_eval_pod_gpu.slurm
```

## Initial Tile Queue

The first specific queue for this repo is:

- gold validation tiles to fully label from scratch:
  - `runs/new_method/rse2023_2015_v1/manual_labels/queues/2015_gold_val_tiles_v1.txt`
- reviewed training tiles to correct weak labels:
  - `runs/new_method/rse2023_2015_v1/manual_labels/queues/2015_train_review_tiles_v1.txt`
- hard-review tiles to inspect for false positives and ambiguous cases:
  - `runs/new_method/rse2023_2015_v1/manual_labels/queues/2015_hard_review_tiles_v1.txt`

These were chosen from:

- the fixed explicit validation split in
  `runs/new_method/rse2023_2015_v1/splits/2015_ssa_val_v1/val_tiles.txt`
- the 2015 tile difficulty statistics in
  `runs/new_method/rse2023_2015_v1/splits/2015_ssa_val_v1/tile_stats.csv`

## Decision Summary

For the current repo and model family:

- polygon labels are the correct manual geometry
- point labels are not enough
- bounding boxes are not the right annotation type for the current training
  path
