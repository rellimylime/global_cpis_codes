# Workspace Index (Post-Cleanup)

Last updated: 2026-03-09

## Quick Navigation

- `START_HERE.md`
- `README.md`

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
- Current paper-method review outputs:
  - `runs/paper_method/recommended/tile0816_fixed_t085/`
  - `runs/paper_method/recommended/tile0816_fixed_t085/final/no_radius_mode/`
- New method run root:
  - `runs/new_method/centerpoint_v1/`
- New method docs:
  - `docs/new_method/README.md`

## Active Final Outputs (No Radius Inference Mode)

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
