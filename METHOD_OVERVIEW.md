# Method Overview (Current State)

This file describes the currently active CPI workflow artifacts in this repo.

## A) Paper-Method Calibration Track (Current Active)

Objective:

- Calibrate detections for a target tile and keep reviewed outputs easy to inspect.

Current tile package:

- `runs/paper_method/recommended/tile0816_fixed_t085/`

Main steps used:

1. Run segmentation-based detections across preprocessing/chip variants.
2. Build consensus/union vector layers.
3. Manual review in QGIS.
4. Keep final output in no-radius mode:
   - confirmed polygons from model
   - manually-added missed pivots as points

Recommended final output path:

- `runs/paper_method/recommended/tile0816_fixed_t085/final/no_radius_mode/`

## B) Why "No Radius Mode"

- Radius inference for manual missed points was intentionally disabled.
- Manual missed pivots are represented as center points only.
- This avoids introducing geometric assumptions not directly supported by labels.

## C) Code Entry Points

- Main CLI:
  - `cpis.py`
- QA/build helpers:
  - `tools/qa/`
- Cleanup/inventory helpers:
  - `tools/cleanup/finalize_locked_cleanup.ps1`
  - `tools/cleanup/generate_archive_manifest.py`

## D) Archive Policy

- Historical outputs/logs are archived under:
  - `archive/2026-03-09_cleanup/`
- Archive is intended as read-only provenance storage.

For details:

- `archive/2026-03-09_cleanup/README.md`
- `archive/2026-03-09_cleanup/ARCHIVE_MANIFEST.json`

## E) New Method Bootstrap (centerpoint_v1)

Fresh-start path:

- `docs/new_method/README.md`
- `tools/new_method/bootstrap_centerpoint_v1.py`
- `runs/new_method/centerpoint_v1/`

This method uses point supervision first, then optionally trains a classifier
from transferred labels to candidate rows.
