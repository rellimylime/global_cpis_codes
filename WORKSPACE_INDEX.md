# Workspace Index (Post-Cleanup)

Last updated: 2026-04-06

## Quick Navigation

- `START_HERE.md`
- `CLAUDE_CODE_HANDOFF.md`
- `README.md`
- `docs/references/chen_et_al/`

## Active Working Areas

- Code:
  - `src/cpis/`
  - `tools/qa/`
  - `tools/new_method/`
  - `cpis.py`
- Config:
  - `configs/defaults.yaml`
  - `configs/ssa_countries.yaml`
- Region assets:
  - `assets/regions/`
- Test imagery:
  - `imgs_test/`
- Legacy paper-method review outputs:
  - `runs/paper_method/recommended/tile0816_fixed_t085/`
  - `runs/paper_method/recommended/tile0816_fixed_t085/final/no_radius_mode/`
- New method run root:
  - `runs/new_method/centerpoint_v1/`
  - `runs/new_method/rse2023_2015_v1/`
- New method docs:
  - `docs/new_method/README.md`
  - `docs/new_method/workflow.md`
  - `docs/new_method/workflow_file_inventory.md`
  - `docs/new_method/rse2023_2015_v1.md`
  - `docs/new_method/ignore_rules.md`

Repo root is intentionally kept narrow after cleanup. The active surface should
mostly be:

- code and configs
- docs
- `runs/`
- `archive/`
- `imgs_cache_raw/`
- `imgs_cache_u8/`
- the current top-level active logs

For repo-facing orientation, prefer `CLAUDE_CODE_HANDOFF.md` over raw runtime
artifacts. Most measured state still lives in local `runs/` outputs and logs,
but the handoff doc summarizes the parts that are safe and useful to push.

## Legacy Final Outputs (No Radius Inference Mode)

Convenience package (single folder):

- `outputs/final_packages/tile0816_no_radius_20260309/`

- Confirmed polygons only:
  - `runs/paper_method/recommended/tile0816_fixed_t085/final/no_radius_mode/tile0816_confirmed_polygons_only.shp`
- Manual missed pivots as points:
  - `runs/paper_method/recommended/tile0816_fixed_t085/final/no_radius_mode/tile0816_manual_missed_points_clean.shp`
- Combined centers (points only):
  - `runs/paper_method/recommended/tile0816_fixed_t085/final/no_radius_mode/tile0816_centers_combined_no_radius.shp`
  - `runs/paper_method/recommended/tile0816_fixed_t085/final/no_radius_mode/tile0816_centers_combined_no_radius.gpkg`
- Summary:
  - `runs/paper_method/recommended/tile0816_fixed_t085/final/no_radius_mode/tile0816_no_radius_mode_summary.json`

## Archived During Cleanup

Archive root:

- `archive/2026-03-09_cleanup/`
- `archive/2026-03-18_workspace_cleanup/`
- `archive/2026-03-18_whole_house_cleanup/`

Main archive buckets:

- `archive/2026-03-09_cleanup/runs_paper_method_legacy/`
- `archive/2026-03-09_cleanup/runs_legacy/`
- `archive/2026-03-09_cleanup/legacy_logs/`
- `archive/2026-03-09_cleanup/legacy_results/`
- `archive/2026-03-09_cleanup/legacy_state/`
- `archive/2026-03-09_cleanup/legacy_docs/`
- `archive/2026-03-09_cleanup/leftover_empty_dirs/`

Archive documentation and inventory:

- `archive/2026-03-09_cleanup/README.md`
- `archive/2026-03-09_cleanup/ARCHIVE_MANIFEST.json`
- `archive/2026-03-09_cleanup/ARCHIVE_MANIFEST.csv`
- `archive/2026-03-18_workspace_cleanup/README.md`
- `archive/2026-03-18_workspace_cleanup/ARCHIVE_SUMMARY.json`
- `archive/2026-03-18_workspace_cleanup/MANIFEST.txt`
- `archive/2026-03-18_whole_house_cleanup/README.md`
- `archive/2026-03-18_whole_house_cleanup/ARCHIVE_SUMMARY.json`
- `archive/2026-03-18_whole_house_cleanup/MANIFEST.txt`

Home-directory cleanup outside the repo:

- `/home/ermiller/archive/2026-03-18_home_cleanup/`

Current live top-level run logs after the 2026-03-18 cleanup:

- local-only `cpis_*.log` / `cpis_*.err` files may appear during active jobs
- they are useful for debugging but not meant to be the primary repo handoff

Most recent completed refine logs were archived to:

- `archive/2026-03-18_workspace_cleanup/top_level_logs/cpis_2015_aug_refine_176750.log`
- `archive/2026-03-18_workspace_cleanup/top_level_logs/cpis_2015_aug_refine_176750.err`

## Pending Locked Items

None at the moment. Previously locked paths were moved out during cleanup.

If new locks happen in future cleanup passes, use:

- `powershell -ExecutionPolicy Bypass -File tools/cleanup/finalize_locked_cleanup.ps1`
- `python tools/cleanup/generate_archive_manifest.py` (refresh archive inventory)

## How the Current Model Workflow is Organized

1. Build paper-method comparison layers:
   - `tools/qa/build_paper_recommended_layers.py`
2. Validate consensus outputs in QGIS.
3. Keep missed pivots as manual center points (no radius assumptions).
4. Use point labels to improve model training in later rounds.

## Quick Commands

List main active outputs:

```bash
Get-ChildItem runs/paper_method/recommended/tile0816_fixed_t085/final/no_radius_mode
```

Show available CLI modules:

```bash
python cpis.py --help
```
