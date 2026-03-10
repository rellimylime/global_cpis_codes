# Start Here

This repo was cleaned on 2026-03-09 to separate active work from historical artifacts.

## 1) Active Files You Should Use

- Workspace map:
  - `WORKSPACE_INDEX.md`
- Method summary:
  - `METHOD_OVERVIEW.md`
- Server handoff/provenance:
  - `SERVER_AI_HANDOFF.md`
- Main code entrypoint:
  - `cpis.py`
- Active detection deliverables (tile 0816, no-radius mode):
  - `runs/paper_method/recommended/tile0816_fixed_t085/final/no_radius_mode/`
  - `outputs/final_packages/tile0816_no_radius_20260309/` (single packaged folder)

## 2) Archive (Historical/Reference)

- Root:
  - `archive/2026-03-09_cleanup/`
- Archive index:
  - `archive/2026-03-09_cleanup/README.md`
- Archive manifest:
  - `archive/2026-03-09_cleanup/ARCHIVE_MANIFEST.json`
  - `archive/2026-03-09_cleanup/ARCHIVE_MANIFEST.csv`

## 3) Rule of Thumb

- Use `runs/paper_method/recommended/.../no_radius_mode/` for current outputs.
- Treat `archive/2026-03-09_cleanup/` as read-only historical storage.

## 4) New Method Track

- `docs/new_method/README.md`
- `tools/new_method/bootstrap_centerpoint_v1.py`
- `runs/new_method/centerpoint_v1/`
