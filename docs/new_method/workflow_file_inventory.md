# 2015 Workflow File Inventory

Last updated: 2026-04-06

This is the current file inventory for the active 2015 arid-SSA CPI workflow.
It is meant to answer: "which files does this workflow actually use right now?"

This is not a full archive of every experiment. It lists the current active
inputs, scripts, configs, and generated artifacts that matter to the workflow.

## Core Docs

- workspace start point:
  - `START_HERE.md`
- push-safe current-state summary:
  - `CLAUDE_CODE_HANDOFF.md`
- runbook:
  - `docs/new_method/rse2023_2015_v1.md`
- decision log:
  - `docs/new_method/workflow.md`
- ignore / exclusion rules:
  - `docs/new_method/ignore_rules.md`
- manual-labeling guidance:
  - `docs/new_method/labeling_plan.md`
- this inventory:
  - `docs/new_method/workflow_file_inventory.md`
- workspace pointer:
  - `WORKSPACE_INDEX.md`

## Main Entry Points

- top-level CLI:
  - `cpis.py`
- GEE export implementation:
  - `src/cpis/gee/export_year.py`
- anchor-truth preparation:
  - `src/cpis/qa/prepare_anchor_truth.py`
- dataset builder:
  - `tools/new_method/build_paper_dataset.py`
- explicit validation split selector:
  - `tools/new_method/select_val_tiles.py`
- manual-train label merge:
  - `tools/new_method/merge_train_review_labels.py`
- V6 label / holdout split helper:
  - `tools/new_method/prepare_v6_labels.py`
- model training wrapper:
  - `tools/new_method/train_paper_model.py`
- model inference wrapper:
  - `tools/new_method/run_paper_inference.py`
- gold-eval dataset prep:
  - `tools/new_method/prepare_gold_eval.py`
- gold-eval runner:
  - `tools/new_method/run_gold_eval.py`
- active-label tile selector:
  - `tools/new_method/select_active_label_tiles.py`
- active-label false-negative export:
  - `tools/new_method/export_fn_layer.py`
- final inventory normalizer:
  - `tools/new_method/finalize_paper_inventory.py`

## Slurm / Batch Wrappers

- training on Pod GPU:
  - `tools/new_method/train_paper_model_pod_gpu.slurm`
- gold evaluation on Pod GPU:
  - `tools/new_method/run_gold_eval_pod_gpu.slurm`
- active-label inference on Pod GPU:
  - `tools/new_method/run_inference_pod_gpu.slurm`

## Paper-Method Model Assets

- paper-family config:
  - `model/cascade_mask_rcnn_pointrend_cbam.py`
- paper-family checkpoint:
  - `model/cascade_mask_rcnn_pointrend_cbam.pth`
- longer V6 / V7 config:
  - `model/cascade_mask_rcnn_pointrend_cbam_v6.py`

## Source Data And Region Assets

- 2000 anchor inventory:
  - `Africa_CPIS-shp/Africa_CPIS_2000.shp`
- 2021 anchor inventory:
  - `Africa_CPIS-shp/Africa_CPIS_2021.shp`
- active 2015 / 2021 export region:
  - `SSA_Arid_by_Country-shp/SSA_Arid_by_Country.shp`

## Anchor-Truth Package

Run root:

- `runs/new_method/rse2023_2015_v1/anchor_truth/`

Key files:

- summary:
  - `runs/new_method/rse2023_2015_v1/anchor_truth/summary.json`
- normalized 2000 anchors:
  - `runs/new_method/rse2023_2015_v1/anchor_truth/anchors/anchor_2000_normalized.gpkg`
- normalized 2021 anchors:
  - `runs/new_method/rse2023_2015_v1/anchor_truth/anchors/anchor_2021_normalized.gpkg`
- stable pivots:
  - `runs/new_method/rse2023_2015_v1/anchor_truth/overlays/stable_pivots.gpkg`
- change zones:
  - `runs/new_method/rse2023_2015_v1/anchor_truth/overlays/change_zones.gpkg`
- background cells:
  - `runs/new_method/rse2023_2015_v1/anchor_truth/overlays/stable_background_cells.gpkg`
- background points:
  - `runs/new_method/rse2023_2015_v1/anchor_truth/overlays/stable_background_points.gpkg`
- study area:
  - `runs/new_method/rse2023_2015_v1/anchor_truth/overlays/study_area.gpkg`

## Export State

2015 export branch:

- run dir:
  - `runs/new_method/rse2023_2015_v1/exports/2015_ssa/`
- manifest:
  - `runs/new_method/rse2023_2015_v1/exports/2015_ssa/export_manifest.json`

2021 export branch:

- run dir:
  - `runs/new_method/rse2023_2015_v1/exports/2021_ssa/`
- manifest:
  - `runs/new_method/rse2023_2015_v1/exports/2021_ssa/export_manifest.json`

## Imagery Cache

Active 2015 raw cache:

- raw TIFFs:
  - `runs/new_method/rse2023_2015_v1/pilot_2015_ssa/raw/`
- uint8 derivatives:
  - `runs/new_method/rse2023_2015_v1/pilot_2015_ssa/u8/`

Legacy 2021 cache used for the 2021 reproduction branch:

- raw:
  - `imgs_cache_raw/`
- uint8:
  - `imgs_cache_u8/`

Important note:

- `pilot_2015_ssa/raw/` is the canonical local 2015 cache for the active
  workflow.
- `imgs_cache_*` remain local-only legacy caches and should not be mixed into
  the 2015 paper-aligned branch.

## Split Files

2015 fixed validation split:

- val source list:
  - `runs/new_method/rse2023_2015_v1/splits/2015_ssa_val_v1/val_tiles.txt`
- split summary:
  - `runs/new_method/rse2023_2015_v1/splits/2015_ssa_val_v1/selection_summary.json`
- tile statistics:
  - `runs/new_method/rse2023_2015_v1/splits/2015_ssa_val_v1/tile_stats.csv`

2021 reproduction validation split:

- val source list:
  - `runs/new_method/rse2023_2015_v1/splits/2021_repro_val_v1/val_tiles.txt`

## Manual Labels

Manual-label root:

- `runs/new_method/rse2023_2015_v1/manual_labels/`

Current key files:

- original gold validation polygons:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_gold_val_v1.gpkg`
- current V2 gold holdout:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_gold_val_v2_holdout.gpkg`
- first reviewed training polygons:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_review_v1.gpkg`
- expanded reviewed training polygons:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_review_all.gpkg`
- additive augmented training labels:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_augmented_v1.gpkg`
- augmented merge summary:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_augmented_v1_summary.json`
- V6 merged training labels:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_v6_merged.gpkg`
- V7 merged training labels:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_v7_merged.gpkg`
- V7 merge summary:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_v7_merged_summary.json`

Queue files:

- gold validation queue:
  - `runs/new_method/rse2023_2015_v1/manual_labels/queues/2015_gold_val_tiles_v1.txt`
- training review queue:
  - `runs/new_method/rse2023_2015_v1/manual_labels/queues/2015_train_review_tiles_v1.txt`
- hard-review queue:
  - `runs/new_method/rse2023_2015_v1/manual_labels/queues/2015_hard_review_tiles_v1.txt`

## Gold Evaluation Assets

Prepared gold-eval packages:

- first gold package:
  - `runs/new_method/rse2023_2015_v1/gold_eval/2015_gold_val_v1/`
- current V2 holdout package:
  - `runs/new_method/rse2023_2015_v1/gold_eval/2015_gold_val_v2/`

Current key files in the V2 package:

- filtered labels:
  - `runs/new_method/rse2023_2015_v1/gold_eval/2015_gold_val_v2/gold_labels_filtered.gpkg`
- val source list:
  - `runs/new_method/rse2023_2015_v1/gold_eval/2015_gold_val_v2/gold_val_sources.txt`
- package summary:
  - `runs/new_method/rse2023_2015_v1/gold_eval/2015_gold_val_v2/prepare_gold_eval_summary.json`
- COCO-style dataset:
  - `runs/new_method/rse2023_2015_v1/gold_eval/2015_gold_val_v2/dataset/`

Gold-eval run lineage:

- V1 gold eval of the V3 transfer branch:
  - `runs/new_method/rse2023_2015_v1/gold_eval_runs/2015_gold_val_eval_176647/`
- V2 gold eval of the V4 augmented branch:
  - `runs/new_method/rse2023_2015_v1/gold_eval_runs/2015_gold_val_v2_eval_v4_177069/`
- V2 gold eval of the V6 branch:
  - `runs/new_method/rse2023_2015_v1/gold_eval_runs/2015_gold_val_v2_eval_v6_177630/`

Most recent gold-eval run:

- run dir:
  - `runs/new_method/rse2023_2015_v1/gold_eval_runs/2015_gold_val_v2_eval_v6_177630/`
- summary:
  - `runs/new_method/rse2023_2015_v1/gold_eval_runs/2015_gold_val_v2_eval_v6_177630/gold_eval_summary.json`

## Active 2015 Training Datasets

Current dataset roots present locally:

- V6 training dataset:
  - `runs/new_method/rse2023_2015_v1/datasets/2015_ssa_stable_v6/`
- V7 training dataset:
  - `runs/new_method/rse2023_2015_v1/datasets/2015_ssa_stable_v7/`

Current latest 2015 training dataset:

- dataset root:
  - `runs/new_method/rse2023_2015_v1/datasets/2015_ssa_stable_v7/`

2021 reproduction dataset:

- dataset root:
  - `runs/new_method/rse2023_2015_v1/datasets/2021_repro_v1/`
- manifest:
  - `runs/new_method/rse2023_2015_v1/datasets/2021_repro_v1/dataset_manifest.json`

## Model Lineage And Checkpoints

2021 reproduction training:

- run dir:
  - `runs/new_method/rse2023_2015_v1/models/2021_repro_v1_ft_173893/`
- practical checkpoint used downstream:
  - `runs/new_method/rse2023_2015_v1/models/2021_repro_v1_ft_173893/latest.pth`

2015 transfer / refinement branches:

- earlier transfer run:
  - `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v3_from_2021_174031/`
- earlier augmented refinement run:
  - `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v4_aug_refine_176750/`
- best current gold-evaluated branch:
  - `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v6_177071/`
- current latest training branch:
  - `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v7_181015/`

Best current gold-evaluated 2015 checkpoint:

- `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v6_177071/best_segm_mAP_epoch_17.pth`

Current latest 2015 best-validation checkpoint:

- `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v7_181015/best_segm_mAP_epoch_11.pth`

## Active-Label Review Branch

Branch root:

- `runs/new_method/rse2023_2015_v1/active_label_v1/`

Key files:

- selected tile manifest:
  - `runs/new_method/rse2023_2015_v1/active_label_v1/selection_manifest.json`
- staged tiles for inference:
  - `runs/new_method/rse2023_2015_v1/active_label_v1/input_tiles/`
- inference output root:
  - `runs/new_method/rse2023_2015_v1/active_label_v1/inference/`
- inference summary:
  - `runs/new_method/rse2023_2015_v1/active_label_v1/inference/inference_summary.json`
- QGIS found / missed export root:
  - `runs/new_method/rse2023_2015_v1/active_label_v1/qgis_layers/`
- missed pivots:
  - `runs/new_method/rse2023_2015_v1/active_label_v1/qgis_layers/missed_pivots.gpkg`
- found pivots:
  - `runs/new_method/rse2023_2015_v1/active_label_v1/qgis_layers/found_pivots.gpkg`
- predicted polygons:
  - `runs/new_method/rse2023_2015_v1/active_label_v1/qgis_layers/model_predictions.gpkg`

## Evaluation / Compatibility Helpers

- COCO eval shim:
  - `tools/evaluation/eval_file.py`
- COCO eval NumPy compatibility patch area:
  - `tools/evaluation/cocoeval.py`
- training image loader with non-finite sanitization:
  - `mm_scripts/datasets/pipelines/loading.py`
- CPU / GPU training API shim:
  - `mm_scripts/apis/train.py`

## Archive Context

Archived logs and cleanup buckets that still matter for backtracking:

- workspace cleanup archive:
  - `archive/2026-03-18_workspace_cleanup/`
- whole-house cleanup archive:
  - `archive/2026-03-18_whole_house_cleanup/`

These are historical context only. They are not the active workflow surface.

## If You Need The Minimal Set

If you only want the most important files to orient yourself quickly, start
with these:

- `CLAUDE_CODE_HANDOFF.md`
- `docs/new_method/rse2023_2015_v1.md`
- `docs/new_method/workflow.md`
- `docs/new_method/ignore_rules.md`
- `docs/new_method/workflow_file_inventory.md`
