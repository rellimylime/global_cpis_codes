# 2015 CPI Workflow and Decision Log

Last updated: 2026-04-06

This document records the current 2015 center-pivot inventory workflow, the
main method choices made so far, and the engineering/debugging decisions that
changed the implementation. It is the narrative companion to
`docs/new_method/rse2023_2015_v1.md`, which is the shorter runbook.

## Goal

Build a standalone 2015 center-pivot inventory for arid sub-Saharan Africa that
is methodologically comparable to the published 2000 and 2021 inventories.

Primary constraints:

- 2015 must be derived from 2015 imagery, not interpolated from 2000 and 2021.
- The workflow should stay in the same methodological family as Chen et al.
- Outputs should be polygon-first, with centers and equivalent radii derived
  after detection.

## Current Method Choice

Authoritative workflow choice:

- Use the Chen et al. paper-aligned instance-segmentation family already present
  in this repo:
  - `model/cascade_mask_rcnn_pointrend_cbam.py`
  - `tools/new_method/train_paper_model.py`
  - `tools/new_method/run_paper_inference.py`

Why this was chosen:

- The 2000 and 2021 truth layers came from that published workflow family.
- This preserves methodological continuity with the anchor inventories.
- A generic classifier or a different segmentation family would make 2015 less
  directly comparable to the published products.

What was considered and not chosen as the main path:

- Kili blog workflow:
  - useful for annotation/process discipline only
  - not a model recommendation by itself
- Nature Scientific Reports patch classifier:
  - rejected as the main detector because it predicts patch presence/absence,
    not pivot polygons, centers, or radii
- MDPI U-Net style segmentation:
  - useful conceptual baseline, but not chosen as the primary release path
    because comparability with Chen et al. mattered more
- SSA-Pivot-Detect random-forest activity classifier:
  - useful reference for Landsat feature engineering and QA logic
  - not suitable as the main 2015 polygon inventory method

## Current Data Strategy

Anchor truth:

- `Africa_CPIS-shp/Africa_CPIS_2000.shp`
- `Africa_CPIS-shp/Africa_CPIS_2021.shp`

Current interpretation of those layers:

- They are anchor inventories for supervision, QA, and evaluation.
- They are not treated as perfect manual gold labels.
- They are normalized into a common package before analysis.

2015 imagery choice:

- Landsat Collection 2 full-year 2015 composites
- 4-band paper-aligned export contract:
  - `blue, green, red, nir`

Geographic scope:

- arid sub-Saharan Africa only
- current export region:
  - `SSA_Arid_by_Country-shp/SSA_Arid_by_Country.shp`

Why Landsat instead of Sentinel-2:

- Full-year 2015 coverage matters.
- Sentinel-2 is only available for late 2015 onward.
- Landsat keeps one consistent production sensor for the full year.

## Current Directory Contract

Main run root:

- `runs/new_method/rse2023_2015_v1/`

Important subdirectories:

- `runs/new_method/rse2023_2015_v1/anchor_truth/`
- `runs/new_method/rse2023_2015_v1/exports/2015_ssa/`
- `runs/new_method/rse2023_2015_v1/exports/2021_ssa/`
- `runs/new_method/rse2023_2015_v1/pilot_2015_ssa/raw/`
- `runs/new_method/rse2023_2015_v1/pilot_2015_ssa/u8/`
- `runs/new_method/rse2023_2015_v1/datasets/`
- `runs/new_method/rse2023_2015_v1/models/`

Important rule:

- `pilot_2015_ssa/raw/` is the current canonical local cache for 2015 Landsat
  exports in this workflow.
- `drive_downloads/` is only a staging inbox from Google Drive.
- `imgs_cache_raw/` and `imgs_cache_u8/` are older caches and should not be
  mixed with the 2015 Landsat cache.

## Workflow Summary

### 1. Normalize anchor truth

Implemented in:

- `src/cpis/qa/prepare_anchor_truth.py`

Purpose:

- normalize 2000 and 2021 anchors
- recompute equal-area area and equivalent-radius fields
- derive stable/change/background strata

Main outputs:

- `anchor_2000_normalized.gpkg`
- `anchor_2021_normalized.gpkg`
- `stable_pivots.gpkg`
- `change_zones.gpkg`
- `stable_background_cells.gpkg`
- `stable_background_points.gpkg`

Snapshot from 2026-03-11:

- `stable_pivots`: 5,612
- `change_zones`: 2,954
- `stable_background_cells`: 5,465

### 2. Export 2015 Landsat imagery

Implemented in:

- `src/cpis/gee/export_year.py`

Important export choices:

- use `paper_rgbnir_v1`
- use SSA arid-region mask, not the broad anchor-envelope study area
- export in batches with manifest tracking
- skip tiles already present locally

Why the SSA arid-region mask was chosen:

- the anchor-envelope diagnostic layer included large offshore areas
- this caused bad smoke exports over ocean
- the SSA arid-region mask is a production-appropriate AOI

### 2a. Start a parallel 2021 Landsat export branch

Purpose:

- keep a 2021 Landsat cache available for possible 2021 reproduction/fine-tuning
- match the 2015 export contract and AOI instead of relying on the older
  Sentinel-only caches

Current 2021 export branch:

- manifest:
  - `runs/new_method/rse2023_2015_v1/exports/2021_ssa/export_manifest.json`
- drive folder:
  - `CPIS_RSE2023_2021_RGBNIR_SSA`
- feature contract:
  - `paper_rgbnir_v1`
- AOI:
  - `SSA_Arid_by_Country-shp/SSA_Arid_by_Country.shp`

Snapshot from 2026-03-17:

- intersecting tiles: 509
- first batch started: 100 tasks
- manifest status after first batch:
  - `running`: 100
  - `queued`: 409

### 3. Stage downloaded exports into a local 2015 cache

Implemented in:

- `tools/new_method/stage_paper_batch.py`

Purpose:

- move or link raw TIFFs into `pilot_2015_ssa/raw/`
- generate `_rgbnir_u8` versions in `pilot_2015_ssa/u8/`

### 4. Build one-category COCO training data

Implemented in:

- `tools/new_method/build_paper_dataset.py`

Current label choice:

- one-category pivot segmentation using stable pivots as the first weak-label
  source

Why one category:

- current anchor truth available to this workflow does not distinguish completed
  vs incomplete pivots in a way that has been operationalized for training
- a one-category detector is the lowest-risk step toward a usable 2015 model

Current dataset settings:

- chip size: `1024`
- overlap: `128`
- source-raster-level train/val split
- serious reruns should use an explicit validation tile list, not the default
  hash split
- manual labels for this workflow should be polygons, not points or boxes

Manual labeling reference:

- `docs/new_method/labeling_plan.md`

Current dataset snapshot from `2015_ssa_stable_v2`:

- `train_images`: 471
- `val_images`: 96
- `train_annotations`: 6,848
- `val_annotations`: 885
- `sanitized_nonfinite_chips`: 12

### 5. Train the paper-style model

Implemented in:

- `tools/new_method/train_paper_model.py`
- `tools/new_method/train_paper_model_pod_gpu.slurm`

Current training choice:

- fine-tune from the local paper checkpoint by default:
  - `model/cascade_mask_rcnn_pointrend_cbam.pth`

Why this changed:

- the initial smoke run trained from scratch
- that proved the pipeline worked end to end
- for quality-focused reruns, fine-tuning from the existing paper checkpoint is
  a better default than a cold start

### 6. Run inference and later finalize 2015 inventory

Implemented in:

- `tools/new_method/run_paper_inference.py`
- `tools/new_method/finalize_paper_inventory.py`

Purpose:

- inference on 4-band TIFF directories
- later conversion of reviewed 2015 polygons into the release schema

## Main Engineering Decisions and Fixes So Far

### Anchor-truth preparation fixes

Problems found:

- invalid topology in dissolved exclusion geometries
- background cells touching or overlapping excluded layers in unintended ways
- missing `log` callback bug

Changes made:

- repair invalid geometries before predicate checks
- use prepared geometry for repeated checks
- tighten background-layer generation logic
- add more stage logging

Result:

- anchor prep now finishes successfully on the Africa-wide truth layers

### Export-manifest improvements

Problems found:

- restarted batches tried to begin again from earlier tile ids
- exporter only knew manifest state, not what was already downloaded locally

Changes made:

- added `--max-start-tasks`
- added `--skip-local-dir`
- improved local tile scanning using `tile_XXXXXX` naming

Result:

- task submission can continue in batches without re-queuing already-downloaded
  tiles

### Dataset-builder improvements

Problems found:

- early train/val split could assign all source rasters to train
- some image chips contained non-finite values
- validation split was pseudo-random and weak for real experiments

Changes made:

- guarantee at least one validation source when `val_fraction > 0`
- sanitize non-finite chip values on write
- record `sanitized_nonfinite_chips` in the dataset manifest
- add explicit validation-source control via `--val-sources-file`
- add per-source stats to the dataset manifest

Result:

- dataset generation is now stable and can support a fixed holdout set

Additional 2026-03-17 change:

- chunked GEE exports such as `africa_s2_2021_tile_0023-0000000000-0000011776`
  are now grouped back to their parent source tile for split assignment
- this prevents train/val leakage across the four chunk files that belong to the
  same parent GEE tile
- the same chunk-grouping rule is now used by `select_val_tiles.py`

### Explicit validation selection

Implemented in:

- `tools/new_method/select_val_tiles.py`

Purpose:

- generate a reusable `val_tiles.txt` from the current 2015 raw-tile cache
- seed validation selection across geographic bins
- favor tiles with enough stable-pivot signal to make validation meaningful
- mix easier and harder positive tiles using a simple difficulty score

Current `2015_ssa_val_v1` selection summary:

- raw tiles considered: 203
- positive tiles considered: 53
- selected validation tiles: 13
- tier mix:
  - 6 high
  - 5 medium
  - 2 low

Current selected validation tiles:

- `cpis_landsat_2015_tile_000006`
- `cpis_landsat_2015_tile_000010`
- `cpis_landsat_2015_tile_000015`
- `cpis_landsat_2015_tile_000022`
- `cpis_landsat_2015_tile_000026`
- `cpis_landsat_2015_tile_000033`
- `cpis_landsat_2015_tile_000045`
- `cpis_landsat_2015_tile_000069`
- `cpis_landsat_2015_tile_000091`
- `cpis_landsat_2015_tile_000101`
- `cpis_landsat_2015_tile_000104`
- `cpis_landsat_2015_tile_000106`
- `cpis_landsat_2015_tile_000120`

### 2026-03-16 status update

New dataset rebuild using the explicit validation split:

- dataset root:
  - `runs/new_method/rse2023_2015_v1/datasets/2015_ssa_stable_v3/`
- source tiles considered:
  - 203
- validation source tiles:
  - 13
- dataset totals:
  - `train_images`: 420
  - `val_images`: 221
  - `train_annotations`: 5,256
  - `val_annotations`: 2,723
  - `sanitized_nonfinite_chips`: 12

Interpretation:

- the validation set is now much stronger than the original smoke split
- validation now holds out several dense positive tiles on purpose
- this makes the next metric harder, but much more trustworthy

Next training run launched:

- Slurm job:
  - `173779`
- model tag:
  - `2015_ssa_stable_v3_ft`
- settings:
  - fine-tune from `model/cascade_mask_rcnn_pointrend_cbam.pth`
  - `total_epochs=20`
  - `optimizer_lr=0.0005`
  - `grad_clip_max_norm=5`

### 2026-03-17 status update

2015 fine-tune outcome:

- the `2015_ssa_stable_v3_ft` run improved substantially over the earlier smoke
  baseline, but validation plateaued late in training
- late-epoch segmentation validation values:
  - epoch 18: `segm_mAP=0.1493`, `segm_mAP_50=0.2510`
  - epoch 19: `segm_mAP=0.1504`, `segm_mAP_50=0.2594`
  - epoch 20: `segm_mAP=0.1383`, `segm_mAP_50=0.2397`

Interpretation:

- the 2015 weak-label path is now working, but it appears to be approaching the
  limit of what it can do without stronger supervision
- this was the trigger for starting the 2021 direct-supervision branch

2021 branch actions started:

- generated a fixed 2021 validation split from the existing `imgs_cache_raw`
  cache after collapsing 4-way GEE chunk files back to parent source tiles
- current `2021_repro_val_v1` snapshot:
  - grouped source tiles in cache: 214
  - positive source tiles: 48
  - selected validation tiles: 10
- started building:
  - `runs/new_method/rse2023_2015_v1/datasets/2021_repro_v1/`
  using:
  - imagery: `imgs_cache_raw/`
  - labels: `Africa_CPIS-shp/Africa_CPIS_2021.shp`
  - fixed val list:
    `runs/new_method/rse2023_2015_v1/splits/2021_repro_val_v1/val_tiles.txt`

2021 training outcome:

- work dir:
  - `runs/new_method/rse2023_2015_v1/models/2021_repro_v1_ft_173893/`
- final epoch-20 validation:
  - `segm_mAP=0.6051`
  - `segm_mAP_50=0.7391`
  - `segm_mAP_75=0.6870`
- best recent validation was epoch 19:
  - `segm_mAP=0.6082`
  - `segm_mAP_50=0.7398`

Interpretation:

- direct 2021 supervision is dramatically stronger than the weak-label 2015-only
  path
- this makes the 2021 fine-tuned checkpoint the new preferred starting point for
  the next 2015 transfer run

Current next experiment:

- fine-tune the 2015 dataset from:
  - `runs/new_method/rse2023_2015_v1/models/2021_repro_v1_ft_173893/latest.pth`
- rather than from the generic paper checkpoint:
  - `model/cascade_mask_rcnn_pointrend_cbam.pth`

### Training-wrapper improvements

Problems found:

- import path bug caused the top-level `cpis.py` file to shadow the package
- scripts assumed CUDA was always available
- stats computation could return `NaN`
- missing `tensorboard` broke training at startup
- config/runtime compatibility issues with legacy `nms_thr` and `max_num`
- evaluation code had pycocotools and NumPy compatibility issues

Changes made:

- fixed import path handling
- added CPU/CUDA selection
- filter non-finite pixels during stats computation
- remove unavailable `TensorboardLoggerHook`
- translate legacy config fields at runtime
- patch evaluation helpers for `getCatIds/getImgIds`
- patch deprecated `np.float`
- sanitize non-finite pixels again in the MMDetection data loader
- enable best-checkpoint saving on validated runs with `save_best=segm_mAP`
  and `rule=greater`

Result:

- the training/evaluation path now runs end to end on the GPU cluster
- future validated runs keep a best model checkpoint in addition to `latest.pth`

## What the First Successful 2015 Smoke Run Proved

Successful run:

- `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v1_smoke_173126/`

What it proved:

- the data path works
- the model config can be adapted to the one-category dataset
- training can run stably on Pod GPU nodes
- validation can complete and write result files

Why it is not the final modeling setup:

- it was only a 6-epoch smoke run
- it used a weak train/val split
- it was mainly a pipeline proof, not a quality-optimized experiment

Final smoke-run metric snapshot:

- `segm_mAP`: 0.0034
- `segm_mAP_50`: 0.0078

Interpretation:

- pipeline success
- model-quality failure
- next steps should focus on better data and better experiment design, not more
  basic runtime debugging

## Current Next-Step Strategy

Do before the next serious rerun:

1. Continue 2015 export/download/staging until the local 2015 cache is much
   larger than the original 98-tile pilot.
2. Build an explicit validation tile list instead of using the pseudo-random
   source split.
3. Rebuild the dataset from the enlarged local 2015 cache using that fixed
   validation list.
4. Fine-tune from `model/cascade_mask_rcnn_pointrend_cbam.pth` with a lower
   learning rate and gradient clipping.

Current rerun threshold:

- do not rerun immediately after every small batch
- prefer rerunning once the local 2015 raw cache is around 180+ tiles and the
  dataset has been rebuilt with an explicit validation set

## 2021 Branch Status

Why this branch was started:

- if the 2015 weak-label path plateaus, a direct 2021 reproduction dataset may
  be the next strongest pretraining step
- starting the 2021 exports early avoids waiting on GEE later if that branch is
  needed

Current decision:

- continue the active 2015 fine-tune as the primary experiment
- keep the 2021 Landsat export branch running in parallel as a hedge
- do not switch the main experiment to 2021 unless current 2015 results plateau
  after failure analysis

## Manual Gold Validation Status

Current gold validation package:

- `runs/new_method/rse2023_2015_v1/manual_labels/2015_gold_val_v1.gpkg`

Current manually labeled tiles:

- `cpis_landsat_2015_tile_000015`
- `cpis_landsat_2015_tile_000022`
- `cpis_landsat_2015_tile_000026`
- `cpis_landsat_2015_tile_000033`

Gold evaluation dataset prepared at:

- `runs/new_method/rse2023_2015_v1/gold_eval/2015_gold_val_v1/`

Gold evaluation snapshot from 2026-03-18:

- gold dataset totals:
  - `val_images`: 288
  - `val_annotations`: 2,754
- checkpoint evaluated:
  - `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v3_from_2021_174031/best_segm_mAP_epoch_19.pth`
- gold segmentation metrics:
  - `AP@[0.50:0.95] = 0.223`
  - `AP@0.50 = 0.439`
  - `AP@0.75 = 0.194`
  - `AR@[0.50:0.95] = 0.361`

Interpretation:

- this manual holdout score is materially higher than the weak-label 2015
  validation score
- the model is still not strong enough, but the weak-label validation was
  likely understating performance
- the main bottleneck remains 2015 supervision quality, not basic training
  viability

## 2026-03-18 Manual Training Labels

Added first reviewed training layer:

- `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_review_v1.gpkg`

Current contents:

- `663` confirmed polygons
- source tiles:
  - `cpis_landsat_2015_tile_000023`
  - `cpis_landsat_2015_tile_000024`
  - `cpis_landsat_2015_tile_000035`

Merge helper added:

- `tools/new_method/merge_train_review_labels.py`

Important rule:

- fully reviewed training tiles can replace weak labels on those tiles
- partial "obvious-only" manual labels should not replace all weak labels on a
  tile, because unlabeled true pivots would be treated as background during
  training

## 2026-03-18 Augmented 2015 Retraining Branch

To use the partial reviewed training polygons safely, the merge logic was
switched to additive augmentation rather than full tile replacement.

Files:

- manual reviewed training labels:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_review_v1.gpkg`
- augmented merged labels:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_augmented_v1.gpkg`
- merge summary:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_augmented_v1_summary.json`

Augmented merge result:

- `weak_in = 5612`
- `weak_reviewed = 1662`
- `weak_removed = 258`
- `manual_added = 663`
- `merged = 6017`

New 2015 dataset built from augmented labels:

- dataset root:
  - `runs/new_method/rse2023_2015_v1/datasets/2015_ssa_stable_v4_augtrain`
- totals:
  - `train_images = 433`
  - `val_images = 221`
  - `train_annotations = 5893`
  - `val_annotations = 2723`

Compared with `v3`, this added training signal without changing the fixed
validation split.

Current refinement run:

- Slurm job: `176750`
- job name: `cpis_2015_aug_refine`
- work dir:
  - `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v4_aug_refine_176750`
- initialization checkpoint:
  - `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v3_from_2021_174031/best_segm_mAP_epoch_19.pth`
- settings:
  - `total_epochs = 12`
  - `optimizer_lr = 0.0001`
  - `grad_clip_max_norm = 5`

## 2026-03-20 V6 Label And Training Update

The next step after the `v4` augmented branch was to move part of the reviewed
gold pool into training while keeping a smaller manual holdout for real gold
evaluation.

Files:

- label prep helper:
  - `tools/new_method/prepare_v6_labels.py`
- new merged training labels:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_v6_merged.gpkg`
- updated holdout labels:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_gold_val_v2_holdout.gpkg`
- training config:
  - `model/cascade_mask_rcnn_pointrend_cbam_v6.py`

V6 label split:

- moved into training:
  - `cpis_landsat_2015_tile_000022`
  - `cpis_landsat_2015_tile_000026`
- kept as gold holdout:
  - `cpis_landsat_2015_tile_000015`
  - `cpis_landsat_2015_tile_000033`

V6 training run:

- work dir:
  - `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v6_177071/`
- best validation checkpoint was epoch 17:
  - `segm_mAP = 0.1456`
  - `segm_mAP_50 = 0.2518`
  - `segm_mAP_75 = 0.1523`
- final epoch 36 had regressed:
  - `segm_mAP = 0.1166`
  - `segm_mAP_50 = 0.2105`
  - `segm_mAP_75 = 0.1175`

Interpretation:

- validation still decayed late in training, so early best-checkpoint selection
  mattered more than the final epoch
- the V6 branch was useful mainly because it created a cleaner gold-holdout
  comparison point than the earlier `v1` gold package

## 2026-03-22 V6 Gold Holdout Evaluation

Files:

- gold package:
  - `runs/new_method/rse2023_2015_v1/gold_eval/2015_gold_val_v2/`
- eval run:
  - `runs/new_method/rse2023_2015_v1/gold_eval_runs/2015_gold_val_v2_eval_v6_177630/`

Metrics from the V6 best checkpoint on the `v2` holdout:

- `AP@[0.50:0.95] = 0.2505`
- `AP@0.50 = 0.4870`
- `AP@0.75 = 0.2350`
- `AR@[0.50:0.95] = 0.3838`

Interpretation:

- this was the best confirmed 2015 gold-holdout result so far
- the gain over `v4` was modest, but it was consistent enough to treat V6 as
  the current best gold-evaluated branch

## 2026-03-24 To 2026-03-25 Active-Label Branch

The next manual-label round was set up as an active-label branch rather than
another generic queue.

Files:

- tile selection:
  - `tools/new_method/select_active_label_tiles.py`
- selection manifest:
  - `runs/new_method/rse2023_2015_v1/active_label_v1/selection_manifest.json`
- inference summary:
  - `runs/new_method/rse2023_2015_v1/active_label_v1/inference/inference_summary.json`
- QGIS false-negative export:
  - `tools/new_method/export_fn_layer.py`

Selected tiles:

- `000059`
- `000095`
- `000005`
- `000009`
- `000107`
- `000032`
- `000036`
- `000025`
- `000014`
- `000001`
- `000044`
- `000016`

Inference status:

- all 12 selected tiles were processed successfully
- there were no failed tiles
- there were no `no_detection` tiles

Important caveat:

- `tools/new_method/select_active_label_tiles.py` excludes a hardcoded
  `ALREADY_LABELED` set
- that list was correct for the earlier reviewed set, but it is now stale
  relative to the later `v7` reviewed-source summary
- future active-label selection should derive exclusions from the reviewed label
  outputs instead of keeping the hardcoded list

## 2026-03-26 V7 Manual-Review Expansion

The next branch expanded the reviewed training pool substantially beyond the
earlier 3-tile augmented merge.

Files:

- expanded reviewed training labels:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_review_all.gpkg`
- merged summary:
  - `runs/new_method/rse2023_2015_v1/manual_labels/2015_train_v7_merged_summary.json`
- current latest training run:
  - `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v7_181015/`

V7 merge summary:

- reviewed sources: `15`
- weak labels intersecting reviewed sources: `2938`
- weak labels removed: `906`
- manual labels selected: `3469`
- merged label count: `8175`

V7 training run:

- best validation checkpoint was epoch 11:
  - `segm_mAP = 0.1537`
  - `segm_mAP_50 = 0.2565`
  - `segm_mAP_75 = 0.1693`
- final epoch 36:
  - `segm_mAP = 0.1293`
  - `segm_mAP_50 = 0.2268`
  - `segm_mAP_75 = 0.1386`

Interpretation:

- V7 is the current latest 2015 training branch
- its best validation was slightly better than V6, but it still shows late
  regression
- there is not yet a gold-holdout evaluation for V7, so it is not yet the
  best confirmed 2015 model

## Definitions Used in This Workflow

Train:

- the subset used to update model weights

Validation:

- the held-out subset used during training to measure generalization on unseen
  source tiles

Learning rate:

- the size of each optimizer update step

Epoch:

- one full pass through the training dataset

Gradient clipping:

- a safeguard that limits very large gradient updates to reduce training
  instability

Explicit validation list:

- a newline-delimited text file containing exact source raster stems that must
  go into validation

## Files to Keep Updated

Primary runbook:

- `docs/new_method/rse2023_2015_v1.md`

This decision log:

- `docs/new_method/workflow.md`

Current file inventory:

- `docs/new_method/workflow_file_inventory.md`

High-level workspace pointer:

- `WORKSPACE_INDEX.md`

## 2026-03-18 Workspace Cleanup

Non-active artifacts were moved into:

- `archive/2026-03-18_workspace_cleanup/`

What was archived:

- completed top-level training and evaluation logs
- old `slurm-*.out` files
- the abandoned Hough-labeling pilot branch
- Hough-only manual-label queue files
- the old top-level `INFO` file

What initially stayed live:

- `cpis_2015_aug_refine_176750.log`
- `cpis_2015_aug_refine_176750.err`
- all active files under `runs/new_method/rse2023_2015_v1/`
- current docs under `docs/new_method/`

After the refine run completed, those top-level logs were also archived to:

- `archive/2026-03-18_workspace_cleanup/top_level_logs/cpis_2015_aug_refine_176750.log`
- `archive/2026-03-18_workspace_cleanup/top_level_logs/cpis_2015_aug_refine_176750.err`

## 2026-03-18 Whole-House Cleanup

A second cleanup pass moved higher-noise legacy items into:

- `archive/2026-03-18_whole_house_cleanup/`

This pass archived:

- legacy root scripts from the older Africa-wide pipeline
- old root metadata/state files
- one-off scratch directories from earlier experiments
- early 2015 smoke artifacts under `runs/new_method/rse2023_2015_v1/`
- the transient `drive_downloads/` inbox

The active 2015 workflow surface after this cleanup is meant to be:

- `runs/new_method/rse2023_2015_v1/pilot_2015_ssa/`
- `runs/new_method/rse2023_2015_v1/datasets/2015_ssa_stable_v3/`
- `runs/new_method/rse2023_2015_v1/datasets/2015_ssa_stable_v4_augtrain/`
- `runs/new_method/rse2023_2015_v1/datasets/2021_repro_v1/`
- `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v3_from_2021_174031/`
- `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v4_aug_refine_176750/`
- `runs/new_method/rse2023_2015_v1/models/2021_repro_v1_ft_173893/`
