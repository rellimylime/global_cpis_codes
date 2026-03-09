# New Method: centerpoint_v1

This is the fresh-start method track.

Design choice:

- Centerpoint-first supervision from manual point labels.
- No radius inference for manual missed pivots.
- Radius/polygon generation is optional later.

## Directory Contract

- Runs:
  - `runs/new_method/centerpoint_v1/`
- Docs:
  - `docs/new_method/`
- Tools:
  - `tools/new_method/`

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
