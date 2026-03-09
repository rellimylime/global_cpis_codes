# Our Method (Current Working Pipeline)

This folder tracks the current heuristic/candidate-classifier workflow (the one we have been actively debugging).

## Active run/output locations

- Features:
  - `runs/our_method/features/2015_validation2_landmasked_v2`
- Label packs:
  - `runs/our_method/labeling/2015_validation2_landmasked_v2`
  - `runs/our_method/labeling/2015_validation2_landmasked_v2_easy`
- Reports:
  - `runs/our_method/reports`

## Core command pattern

```bash
python cpis.py features generate-candidates \
  --year 2015 \
  --input-dir data/composites/2015/validation2 \
  --out-dir runs/our_method/features/2015_validation2_landmasked_v2 \
  --region-mask assets/regions/arid_ssa.geojson \
  --exclude-water \
  --water-ndwi-threshold 0.0

python cpis.py qa make-label-pack \
  --candidates runs/our_method/features/2015_validation2_landmasked_v2/candidates.csv \
  --out-dir runs/our_method/labeling/2015_validation2_landmasked_v2 \
  --year 2015 \
  --region-mask assets/regions/arid_ssa.geojson \
  --exclude-water \
  --water-ndwi-threshold 0.0 \
  --sample-n 300
```

## Notes

- This workflow is Landsat-first and currently point/circle candidate based.
- Keep uncertain labels as `-1` during manual review.
