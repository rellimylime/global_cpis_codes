# Server AI Handoff (Legacy Tile 0816 Checkpoint)

This file is for server-side AI agents so they can quickly understand what is
committed, what is authoritative, and how artifacts were produced.

This is a legacy handoff for the older tile-0816 paper-method branch. For the
current active 2015/2021 workflow, use:

- `WORKSPACE_INDEX.md`
- `docs/new_method/workflow.md`
- `docs/new_method/rse2023_2015_v1.md`

## Snapshot

- Branch: `landsat-ssa-v1`
- Latest data checkpoint: `fcc6cae` (`data: add labeled and verified tile0816 artifacts`)
- Area of focus: Sentinel tile `0816`
- Recommended output mode: `no_radius_mode` (manual misses are points, no inferred radius)

## Authoritative Committed Artifacts

1. Primary packaged deliverable (preferred handoff location):
   - `outputs/final_packages/tile0816_no_radius_20260309/`
2. Same deliverable content in run tree:
   - `runs/paper_method/recommended/tile0816_fixed_t085/final/no_radius_mode/`
3. Manual/validated review outputs:
   - `runs/paper_method/recommended/tile0816_fixed_t085/validated/`
   - `runs/paper_method/recommended/tile0816_fixed_t085/final/`
4. Manual anchor points for new-method bootstrap:
   - `runs/new_method/centerpoint_v1/bootstrap_tile0816/labels/manual_points_pos.gpkg`
   - `runs/new_method/centerpoint_v1/bootstrap_tile0816/labels/manual_points_pos.summary.json`
5. Latest edge-aware training table:
   - `data/training/cpi_train_2015_round1_to_round5_with_anchors_600m_override.csv`
   - `data/training/cpi_train_2015_round1_to_round5_with_anchors_600m_override.summary.json`

## What Each Key File Means

1. `tile0816_confirmed_polygons_only.shp`
   - Model-confirmed pivot polygons after review.
2. `tile0816_manual_missed_points_clean.shp`
   - Manually added missed pivots as center points only.
3. `tile0816_centers_combined_no_radius.shp` / `.gpkg`
   - Combined center points (confirmed + manual misses), no radius inference.
4. `tile0816_no_radius_mode_summary.json`
   - Output stats: `base_confirmed_polygons=38`, `manual_missed_points=168`,
     `combined_centers_total=206`.
5. `tile0816_consensus_true.shp` / `tile0816_consensus_false.shp`
   - Manual QA split of consensus detections.
6. `tile0816_extras_to_review.shp`
   - Additional detections flagged for review.
7. `cpi_train_2015_round1_to_round5_with_anchors_600m_override.csv`
   - Classifier training rows with features and labels (`label` in `{0,1}`).

## Provenance (How These Were Generated)

1. Paper-method detection runs were executed across multiple settings/chip sizes
   and thresholds (historical run outputs were large and are not fully tracked).
2. Comparison/recommendation layers were built with:
   - `tools/qa/build_paper_recommended_layers.py`
3. Manual review was done in QGIS, producing:
   - `validated/` (true/false/review splits)
   - `final/` (refined outputs + manual misses)
4. Final recommended deliverable was frozen in `no_radius_mode`:
   - confirmed polygons kept as polygons
   - manual misses kept as points (no inferred geometry/radius)
5. Training table was exported via `cpis.py qa build-train-table` workflow
   (edge-aware settings captured in the `.summary.json` file).

## Rebuild Command Templates

Use these when equivalent source inputs are present:

```bash
# 1) Build fixed-threshold comparison layers (paper-method)
python tools/qa/build_paper_recommended_layers.py \
  --baseline runs/paper_method/tile0816_vector/merged_thr_0p85.shp \
  --run-1536 runs/paper_method/tile0816_vector_chip1536/merged_thr_0p85.shp \
  --run-1024 runs/paper_method/tile0816_vector_chip1024_fixed/merged_thr_0p85.shp \
  --out-dir runs/paper_method/recommended/tile0816_fixed_t085

# 2) Build training CSV from labeled candidates
python cpis.py qa build-train-table \
  --labeled-input runs/our_method/labeling/merged_rounds/label_candidates_round1_to_round5_with_anchors_600m_override.geojson \
  --out-table data/training/cpi_train_2015_round1_to_round5_with_anchors_600m_override.csv \
  --deduplicate \
  --edge-policy positive \
  --edge-status-column review_status \
  --edge-status-values edge \
  --emit-sample-weight \
  --sample-weight-column sample_weight \
  --edge-weight 0.5
```

## Important Reproducibility Notes

1. You can fully use current committed outputs and training CSV on the server
   without rebuilding historical runs.
2. Some historical source paths in summary JSON files are absolute local paths
   from the original workstation and may not exist on the server.
3. Not all intermediate raster/run artifacts are in git (by design for size).
4. For current work, treat the packaged folder below as the frozen reference:
   - `outputs/final_packages/tile0816_no_radius_20260309/`

## Quick Server Verification

```bash
python - <<'PY'
import json, pathlib
base = pathlib.Path("outputs/final_packages/tile0816_no_radius_20260309")
summary = json.loads((base / "tile0816_no_radius_mode_summary.json").read_text())
print("confirmed:", summary["base_confirmed_polygons"])
print("manual:", summary["manual_missed_points"])
print("combined:", summary["combined_centers_total"])
print("ok:", base.exists())
PY
```

## If You Continue Development

1. Use `outputs/final_packages/tile0816_no_radius_20260309/` as baseline.
2. Keep new labels and reviewed outputs in similarly named dated packages.
3. Always add/update a summary JSON when creating a new final layer set.
