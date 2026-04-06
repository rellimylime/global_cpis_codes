# Start Here

This repo was cleaned again on 2026-03-18 to keep the active workflow narrow
and move historical artifacts into archive directories.

## 1) Use These First

- Workspace map:
  - `WORKSPACE_INDEX.md`
- Current push-safe handoff:
  - `CLAUDE_CODE_HANDOFF.md`
- Current workflow docs:
  - `docs/new_method/workflow.md`
  - `docs/new_method/rse2023_2015_v1.md`
  - `docs/new_method/workflow_file_inventory.md`
  - `docs/new_method/labeling_plan.md`
  - `docs/new_method/ignore_rules.md`
- Main code entrypoint:
  - `cpis.py`
- Current active workflow root:
  - `runs/new_method/rse2023_2015_v1/`
- Reference papers:
  - `docs/references/chen_et_al/`

## 2) Treat These As Historical Reference

- Legacy paper-method summary:
  - `METHOD_OVERVIEW.md`
- Legacy tile-0816 handoff:
  - `SERVER_AI_HANDOFF.md`
- Repo archives:
  - `archive/2026-03-09_cleanup/`
  - `archive/2026-03-18_workspace_cleanup/`
  - `archive/2026-03-18_whole_house_cleanup/`

## 3) Rule Of Thumb

- Use `docs/new_method/` plus `runs/new_method/rse2023_2015_v1/` for current work.
- Use `CLAUDE_CODE_HANDOFF.md` when you need a repo-facing current-status
  snapshot, because most runtime artifacts under `runs/` are intentionally not
  the main handoff surface.
- Treat `archive/` as read-only historical storage.
- Treat `METHOD_OVERVIEW.md` and `SERVER_AI_HANDOFF.md` as legacy reference, not
  as the main active workflow.
