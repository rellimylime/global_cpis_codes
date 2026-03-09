# Paper Method (Target Track)

This folder reserves the paper-aligned track based on the ESSD 2025 workflow (Pivot-Net style segmentation approach).

## Intended direction

- Image segmentation first, then vectorization.
- Tile/patch inference with overlap merge.
- Separate evaluation pipeline from the current heuristic method.

## Planned run/output locations

- Features / model artifacts:
  - `runs/paper_method/features`
- Label packs:
  - `runs/paper_method/labeling`
- Reports:
  - `runs/paper_method/reports`
- Design/notes:
  - `runs/paper_method/notes`

## Status

- Directory scaffold created.
- Implementation pending (to avoid mixing assumptions with current production method).

## Quick Comparison (Tile 0816, fixed-scale t=0.85)

Use this helper to compare the three fixed-scale paper-method runs and generate
QGIS-ready recommended layers:

```bash
python tools/qa/build_paper_recommended_layers.py
```

Default outputs:

- `runs/paper_method/recommended/tile0816_fixed_t085/fixed_t085_union_components.shp`
- `runs/paper_method/recommended/tile0816_fixed_t085/fixed_t085_consensus_support2.shp`
- `runs/paper_method/recommended/tile0816_fixed_t085/fixed_t085_consensus_support3.shp`
- `runs/paper_method/recommended/tile0816_fixed_t085/fixed_t085_singleton_support1.shp`
- `runs/paper_method/recommended/tile0816_fixed_t085/summary_fixed_t085.json`
