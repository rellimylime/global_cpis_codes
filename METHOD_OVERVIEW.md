# Method Overview

This repo now has one clearly primary workflow and one legacy reference branch.

## Active Workflow

Use these first:

- `WORKSPACE_INDEX.md`
- `docs/new_method/workflow.md`
- `docs/new_method/rse2023_2015_v1.md`
- `docs/new_method/workflow_file_inventory.md`
- `docs/new_method/labeling_plan.md`

Active run root:

- `runs/new_method/rse2023_2015_v1/`

Primary code entrypoints:

- `cpis.py`
- `src/cpis/`
- `tools/new_method/`

Reference papers:

- `docs/references/chen_et_al/Chen-mapping-center-pivots.pdf`
- `docs/references/chen_et_al/Chen-supplemental.pdf`

## Legacy Reference Branch

The older tile-0816 paper-method review branch is still useful as provenance
and example material, but it is not the main active workflow anymore.

Legacy branch roots:

- `runs/paper_method/recommended/tile0816_fixed_t085/`
- `outputs/final_packages/tile0816_no_radius_20260309/`
- `SERVER_AI_HANDOFF.md`

## Archive Policy

Historical outputs, logs, smoke runs, and cleanup results live under:

- `archive/2026-03-09_cleanup/`
- `archive/2026-03-18_workspace_cleanup/`
- `archive/2026-03-18_whole_house_cleanup/`

Archives are intended as read-only provenance storage.
