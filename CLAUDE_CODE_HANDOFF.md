# Claude Code Handoff

Last updated: 2026-04-06

This file is the push-safe snapshot of where the repo stands right now. It is
meant for a fresh code assistant that needs the current workflow, current
measured status, and the important caveats without reading local Slurm logs
first.

## Read These First

- `START_HERE.md`
- `docs/new_method/workflow.md`
- `docs/new_method/ignore_rules.md`
- `docs/new_method/workflow_file_inventory.md`

## What This Working Tree Is Doing

- The active workflow is now the paper-aligned 2015 / 2021 Landsat path under
  `runs/new_method/rse2023_2015_v1/`.
- The repo root is being cleaned up so the old one-off scripts are treated as
  historical and the current work is concentrated in `src/cpis/`,
  `tools/new_method/`, and `docs/new_method/`.
- There are also several uncommitted helper changes that make the current
  workflow more robust:
  - `src/cpis/cli/main.py` adds `qa prepare-anchor-truth`.
  - `src/cpis/gee/export_year.py` adds `paper_rgbnir_v1`,
    `--skip-local-dir`, and `--max-start-tasks`.
  - `src/cpis/features/generate_candidates.py` and
    `src/cpis/qa/labeling.py` add `--tile-list-file` and related filtering.
  - `mm_scripts/datasets/pipelines/loading.py` sanitizes non-finite chips.
  - `mm_scripts/apis/train.py` now supports CPU/CUDA selection.
  - `tools/evaluation/*` contains compatibility fixes for newer NumPy /
    pycocotools behavior.

## Current Measured Status

Anchor-truth package:

- Runtime summary in `runs/new_method/rse2023_2015_v1/anchor_truth/summary.json`
  currently reports:
  - `stable_pivots = 5612`
  - `change_zones = 2954`
  - `stable_background_cells = 5465`
- Note: older checked-in docs still mention `stable_background_cells = 5152`,
  so use the runtime summary as the current source of truth.

2021 reproduction branch:

- Run:
  - `runs/new_method/rse2023_2015_v1/models/2021_repro_v1_ft_173893/`
- Best observed validation was epoch 19:
  - `segm_mAP = 0.6082`
  - `segm_mAP_50 = 0.7398`
  - `segm_mAP_75 = 0.6900`
- Final epoch 20:
  - `segm_mAP = 0.6051`
  - `segm_mAP_50 = 0.7391`
  - `segm_mAP_75 = 0.6870`
- This is still the strongest source model in the current lineage.

2015 branch, gold-holdout checkpoints:

- `2015_ssa_stable_v3_from_2021_174031`
  evaluated on `2015_gold_val_eval_176647`:
  - `AP@[0.50:0.95] = 0.2230`
  - `AP@0.50 = 0.4394`
  - `AP@0.75 = 0.1935`
  - `AR@[0.50:0.95] = 0.3609`
- `2015_ssa_stable_v4_aug_refine_176750`
  evaluated on `2015_gold_val_v2_eval_v4_177069`:
  - `AP@[0.50:0.95] = 0.2460`
  - `AP@0.50 = 0.4652`
  - `AP@0.75 = 0.2296`
  - `AR@[0.50:0.95] = 0.3567`
- `2015_ssa_stable_v6_177071`
  evaluated on `2015_gold_val_v2_eval_v6_177630`:
  - `AP@[0.50:0.95] = 0.2505`
  - `AP@0.50 = 0.4870`
  - `AP@0.75 = 0.2350`
  - `AR@[0.50:0.95] = 0.3838`

2015 training branches after manual-label expansion:

- V6 run:
  - `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v6_177071/`
  - best validation at epoch 17:
    - `segm_mAP = 0.1456`
    - `segm_mAP_50 = 0.2518`
    - `segm_mAP_75 = 0.1523`
  - final epoch 36:
    - `segm_mAP = 0.1166`
    - `segm_mAP_50 = 0.2105`
    - `segm_mAP_75 = 0.1175`
- V7 run:
  - `runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v7_181015/`
  - best validation at epoch 11:
    - `segm_mAP = 0.1537`
    - `segm_mAP_50 = 0.2565`
    - `segm_mAP_75 = 0.1693`
  - final epoch 36:
    - `segm_mAP = 0.1293`
    - `segm_mAP_50 = 0.2268`
    - `segm_mAP_75 = 0.1386`
- V7 has not been gold-evaluated yet, so it is the newest training branch but
  not yet the best confirmed 2015 model.

Manual label growth:

- `2015_train_augmented_v1_summary.json`:
  - reviewed sources: `3`
  - weak removed: `258`
  - manual added: `663`
  - merged labels: `6017`
- `2015_train_v7_merged_summary.json`:
  - reviewed sources: `15`
  - weak removed: `906`
  - manual added: `3469`
  - merged labels: `8175`

Active-label branch:

- Selection manifest:
  - `runs/new_method/rse2023_2015_v1/active_label_v1/selection_manifest.json`
- 12 tiles were selected for the next manual-review round.
- Inference completed on all 12 tiles using the V6 best checkpoint.
- `inference_summary.json` reports:
  - `processed = 12`
  - `failed = 0`
  - `no_detection = 0`

## Current Interpretation

- The 2021 reproduction branch is healthy and continues to justify using the
  2021-fine-tuned checkpoint as the starting point for 2015 transfer runs.
- On 2015, manual-label expansion is helping, but gains are incremental rather
  than decisive.
- Gold-holdout performance improved from V3 to V4 to V6, which is the strongest
  evidence of real progress right now.
- V7 is promising because the merged training label set is much larger, but
  without a gold-holdout evaluation it is still an unconfirmed branch.

## Important Local-Only Context

- Most runtime artifacts under `runs/` are intentionally not repo-facing due
  `.gitignore`; this file copies the important metrics out of those local
  artifacts.
- Top-level `cpis_*.log` / `cpis_*.err`, `INFO`, `.codex/`, and the legacy
  `imgs_cache_*` directories are local-only.
- `docs/new_method/ignore_rules.md` explains both Git-ignored assets and the
  workflow-side filters that exclude labels, tiles, or detections.

## Known Caveats

- `tools/new_method/select_active_label_tiles.py` has a hardcoded
  `ALREADY_LABELED` set that is stale relative to
  `2015_train_v7_merged_summary.json`.
- `docs/new_method/workflow.md` and
  `docs/new_method/workflow_file_inventory.md` were behind the V6 / V7 state
  before this handoff pass.
- The anchor-truth background-cell count differs between older checked-in docs
  and the current runtime summary.

## Good Next Questions For Planning

- Evaluate the V7 best checkpoint on the current gold holdout before training
  more branches.
- Replace the hardcoded active-label exclusions with a data-driven exclusion
  list derived from the reviewed label summaries or reviewed-source layers.
- Decide when reviewed tiles should switch from `augment` mode to `replace`
  mode in `merge_train_review_labels.py`.
- Keep the 2021 reproduction checkpoint as the default initialization point
  unless a later branch clearly beats it on gold evaluation.
