# New Method: centerpoint_v1

This is the fresh-start method track.

Design choice:

- Centerpoint-first supervision from manual point labels.
- No radius inference for manual missed pivots.
- Radius/polygon generation is optional later.

## Directory Contract

- Runs:
  - `runs/new_method/centerpoint_v1/`
  - `runs/new_method/rse2023_2015_v1/`
- Docs:
  - `docs/new_method/`
- Tools:
  - `tools/new_method/`

## Additional Workflow

- `CLAUDE_CODE_HANDOFF.md`
  - Push-safe current-state snapshot for handing the repo to a fresh code
    assistant without depending on local Slurm logs.
- `docs/new_method/workflow.md`
  - Detailed 2015 CPI workflow and decision log covering method selection,
    engineering fixes, training/debugging history, and current rerun criteria.
- `docs/new_method/workflow_file_inventory.md`
  - Current file-level inventory of the active 2015 workflow inputs, scripts,
    datasets, labels, checkpoints, and generated artifacts.
- `docs/new_method/ignore_rules.md`
  - Explains which artifacts are intentionally local-only plus which labels,
    tiles, and detections are filtered out by the current workflow code.
- `docs/new_method/labeling_plan.md`
  - QGIS-oriented manual labeling plan for 2015 tiles, including why polygons
    are required for the current instance-segmentation pipeline and how to
    structure gold validation vs reviewed training labels.
- `docs/new_method/rse2023_2015_v1.md`
  - Paper-aligned 2015 CPI inventory workflow using the 2000/2021 anchor layers,
    4-band Landsat exports, one-category COCO dataset prep, and final inventory
    normalization.

## Bootstrap Command

Use manual points + candidates to build a train table and optionally train:

```bash
python tools/new_method/bootstrap_centerpoint_v1.py \
  --candidates archive/2026-03-09_cleanup/runs_legacy/our_method/features/2015_validation2_landmasked_v2/candidates.csv \
  --manual-points runs/paper_method/recommended/tile0816_fixed_t085/final/tile0816_manual_missed_points.gpkg \
  --out-root runs/new_method/centerpoint_v1/bootstrap_tile0816 \
  --allow-cross-tile \
  --max-distance-m 600 \
  --train
```

## Outputs (from bootstrap)

- `labels/manual_points_pos.gpkg`
- `labels/manual_points_posneg.gpkg` (if negatives exist)
- `training/centerpoint_v1_train.csv`
- `models/centerpoint_v1_model.meta.json` (if `--train`)
- `bootstrap_summary.json`

## Notes

- If manual points contain only positives (`label=1`), training will still work
  by combining with existing negatives already present in candidate labels.
- To improve classifier balance, include hard negatives (`label=0`) in manual points.
- Candidates must come from the same geography/tile as your manual points.
  If not, bootstrap will stop with `status: no_candidate_matches`.
