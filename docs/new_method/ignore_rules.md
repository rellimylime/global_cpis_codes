# Ignored, Local-Only, And Exclusion Rules

Last updated: 2026-04-06

This document answers two related questions:

- what is intentionally local-only or Git-ignored in this workflow?
- what labels, tiles, or detections get filtered out by workflow code, and why?

## 1) Git-Ignored Or Intentionally Local-Only

Repo-level ignore patterns worth knowing:

- `runs/**`
  - runtime artifacts are ignored by default
  - only the narrow `runs/new_method/rse2023_2015_v1/` path is kept visible so
    the workflow root exists in the repo
- `data/**`
  - local datasets and staging outputs stay out of version control
- `outputs/**`
  - final packages are local unless explicitly carved out
- `archive/**`
  - cleanup archives are treated as local storage, not active repo content
- `.codex/`
  - local assistant scratch state
- `cpis_*.log`, `cpis_*.err`, `INFO`
  - local Slurm / runtime logs
- `imgs_cache_raw/**`, `imgs_cache_u8/**`
  - legacy local image caches used for experiments, not repo-facing state

Important local-but-used inputs:

- `Africa_CPIS-shp/`
  - anchor inventories used for supervision / QA
- `SSA_Arid_by_Country-shp/`
  - current export AOI
- `runs/new_method/rse2023_2015_v1/pilot_2015_ssa/raw/`
  - canonical local 2015 Landsat cache for the active workflow

Important rule of thumb:

- `pilot_2015_ssa/raw/` is the active 2015 imagery cache.
- `drive_downloads/` is only a staging inbox for downloads.
- `imgs_cache_raw/` and `imgs_cache_u8/` are older caches and should not be
  mixed into the 2015 paper-aligned branch by accident.

## 2) Label Filters Used By Training / Eval Prep

`tools/new_method/merge_train_review_labels.py`

- Default manual label filter:
  - `label_set == train`
  - `status in confirmed`
- `merge-mode=replace`
  - manual labels replace weak labels on reviewed tiles entirely
- `merge-mode=augment`
  - weak labels are kept unless their representative point falls within a
    manual polygon
- Why this exists:
  - reviewed tiles are often only partially traced, so `augment` is safer until
    a tile is fully reviewed

`tools/new_method/prepare_gold_eval.py`

- Default gold-label filter:
  - `label_set == val`
  - `status in confirmed`
- Drops empty or missing geometries before dataset build
- Passes through to `build_paper_dataset.py` with:
  - `--val-fraction 0`
  - explicit `gold_val_sources.txt`
- Optional `--keep-empty` keeps empty chips if a true empty eval package is
  desired
- Why this exists:
  - gold evaluation should be built from confirmed validation polygons only

`tools/new_method/prepare_v6_labels.py`

- Moves gold tiles `000022` and `000026` into training
- Keeps gold tiles `000015` and `000033` as holdout
- Why this exists:
  - it creates a larger reviewed training set while preserving a small manual
    holdout for gold evaluation

## 3) Dataset Build Filters

`tools/new_method/build_paper_dataset.py`

- Chips with no intersecting truth polygons are dropped by default
  - `--keep-empty` disables that
- Clipped annotations smaller than `--min-ann-area-px` are dropped
  - default is `16`
- Non-finite chip values are sanitized on write
- Chunked GEE filenames are grouped back to their base tile name for split
  assignment
- `--val-sources-file` overrides hash-based split selection
- Why this exists:
  - avoid train/val leakage, avoid tiny junk polygons, and keep the dataset
    numerically stable

## 4) Candidate And Label-Pack Filters

`src/cpis/features/generate_candidates.py`

- Optional `--tile-list-file`
  - only process listed tiles
- Optional `--region-mask`
  - drop candidates outside the supplied AOI mask
- Optional `--exclude-water`
  - drop candidates whose NDWI center value is above the threshold
- Circle NMS removes overlapping circles after scoring
- Why this exists:
  - keep candidate generation inside the intended geography and reduce obvious
    false positives from water / duplicate circles

`src/cpis/qa/labeling.py`

- Optional `--tile-list-file`
  - only keep listed tile ids
- Optional `--region-mask`
  - drop points outside the AOI
- Optional `--exclude-water`
  - drop likely-water rows using NDWI
- Sampling modes:
  - `stratified`
  - `top`
  - `random`
- `top` favors obvious high-confidence circles
- Why this exists:
  - review queues can be targeted to the geography and difficulty level that
    matters most for the current labeling round

## 5) Export / Inference / Active-Label Exclusions

`src/cpis/gee/export_year.py`

- `--skip-local-dir`
  - scans local TIFF directories and avoids re-submitting already downloaded
    tiles
- `--max-start-tasks`
  - caps task submission in one invocation
- Feature contracts:
  - `stats_v1`
  - `paper_rgbnir_v1`
- Why this exists:
  - resume export batches safely and keep the 2015 / 2021 export contract
    explicit

`tools/new_method/select_active_label_tiles.py`

- Excludes:
  - hardcoded `ALREADY_LABELED`
  - tiles already in validation
  - tiles outside `min_stable` / `max_stable`
- Why this exists:
  - the active-label round should focus on unlabeled training tiles with useful
    stable-pivot signal
- Current caveat:
  - `ALREADY_LABELED` is stale relative to
    `2015_train_v7_merged_summary.json`, so future selection should be updated
    before the next round

`tools/new_method/export_fn_layer.py`

- Marks anchor pivots as `found` when buffered overlap with the prediction union
  is at least `--min-iou`
  - default `min_iou = 0.05`
- Otherwise exports them as `missed`
- Why this exists:
  - it produces the QGIS false-negative review package for active labeling

## 6) Practical Summary

When you are deciding what is safe to push vs what is only local context:

- push docs, scripts, configs, and small manifests that explain the workflow
- do not rely on top-level logs or huge runtime caches as the handoff surface
- treat `CLAUDE_CODE_HANDOFF.md` as the push-safe current-state summary
- treat `runs/`, caches, and local source data as execution context that the
  docs need to describe, not as the primary thing to version
