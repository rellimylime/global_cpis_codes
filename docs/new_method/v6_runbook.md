# V6 Training Runbook

## What changed from V4

| Issue | V4 | V6 |
|---|---|---|
| LR decay | `step=[40]` — never fires in 12 epochs | `step=[24, 32]` — fires twice in 36 epochs |
| Training labels | 6,017 (663 manual on 3 tiles) | ~6,424 (1,070 manual on 5 tiles) |
| Augmentation | H-flip only | H-flip + V-flip (4-fold symmetry for circles) |
| Training epochs | 12 | 36 |

Gold val **holdout** shrinks from 4 tiles (1,689 polygons) to 2 tiles
(000015 + 000033 = 1,282 polygons). Tiles 000022 + 000026 move to training.

---

## Prerequisites

```bash
PY=/home/ermiller/.conda/envs/cpi_fix/bin/python3
export PROJ_LIB=/home/ermiller/.conda/envs/cpi_fix/share/proj
export PROJ_DATA=$PROJ_LIB
cd /home/ermiller/global_cpis_codes
```

---

## Step 1 — Prepare V6 label files

```bash
$PY tools/new_method/prepare_v6_labels.py
```

Outputs to `runs/new_method/rse2023_2015_v1/manual_labels/`:
- `2015_train_v6_merged.gpkg` — ~6,424 training labels
- `2015_gold_val_v2_holdout.gpkg` — 1,282 eval-only labels (tiles 000015 + 000033)

---

## Step 2 — Prepare new gold eval dataset (V2 holdout)

The existing gold eval imagery dir already contains chips from all 4 tiles.
We build a new COCO eval dataset from the holdout-only gpkg:

```bash
GOLD_IMAGERY=runs/new_method/rse2023_2015_v1/pilot_2015_ssa/raw
GOLD_LABELS=runs/new_method/rse2023_2015_v1/manual_labels/2015_gold_val_v2_holdout.gpkg
GOLD_OUT=runs/new_method/rse2023_2015_v1/gold_eval/2015_gold_val_v2

$PY tools/new_method/prepare_gold_eval.py \
  --imagery-dir "$GOLD_IMAGERY" \
  --labels "$GOLD_LABELS" \
  --out-root "$GOLD_OUT" \
  --label-set val \
  --include-status confirmed \
  --keep-empty \
  --copy-mode symlink
```

---

## Step 3 — Build V6 training dataset

```bash
LABELS=runs/new_method/rse2023_2015_v1/manual_labels/2015_train_v6_merged.gpkg
VAL_SPLIT=runs/new_method/rse2023_2015_v1/splits/2015_ssa_val_v1/val_tiles.txt
OUT=runs/new_method/rse2023_2015_v1/datasets/2015_ssa_stable_v6

$PY tools/new_method/build_paper_dataset.py \
  --imagery-dir runs/new_method/rse2023_2015_v1/pilot_2015_ssa/raw \
  --labels "$LABELS" \
  --out-root "$OUT" \
  --chip-size 1024 \
  --chip-overlap 128 \
  --val-sources-file "$VAL_SPLIT" \
  --val-fraction 0.25
```

---

## Step 4 — Submit training job

Start from the best 2021-pretrained checkpoint (same as V4):

```bash
CPIS_CONFIG=model/cascade_mask_rcnn_pointrend_cbam_v6.py \
CPIS_DATASET_ROOT=runs/new_method/rse2023_2015_v1/datasets/2015_ssa_stable_v6 \
CPIS_TOTAL_EPOCHS=36 \
CPIS_CHECKPOINT=runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v3_from_2021_174031/best_segm_mAP_epoch_19.pth \
CPIS_MODEL_TAG=2015_ssa_stable_v6 \
sbatch tools/new_method/train_paper_model_pod_gpu.slurm
```

Note the job ID. Best checkpoint will be saved as `best_segm_mAP_epoch_N.pth`.

---

## Step 5 — Gold-evaluate V6

Once training completes, replace CHECKPOINT_PATH with the V6 best checkpoint:

```bash
CPIS_GOLD_CONFIG=runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v6_<JOBID>/resolved_config.py \
CPIS_GOLD_CHECKPOINT=runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v6_<JOBID>/best_segm_mAP_epoch_N.pth \
CPIS_GOLD_DATASET_ROOT=runs/new_method/rse2023_2015_v1/gold_eval/2015_gold_val_v2/dataset \
CPIS_GOLD_OUT_TAG=2015_gold_val_v2_eval_v6 \
sbatch tools/new_method/run_gold_eval_pod_gpu.slurm
```

---

## Expected improvement trajectory

| Model | Dataset | Epochs | LR decay | Gold AP@0.5 |
|---|---|---|---|---|
| V3 | 5,256 weak | 12 (no decay) | ✗ | 0.439 |
| V4 | 6,017 (663 manual, aug) | 12 (no decay) | ✗ | 0.449 |
| **V6** | ~6,424 (1,070 manual) | 36 (2 decays) | ✓ | ? |

The LR fix alone is expected to be the largest single gain. The additional 407
manual labels on geographically new tiles (000022/000026) improve geographic
generalization.

---

## If V6 still plateaus

Next steps in order of expected impact:
1. Label 3–5 more training tiles (~200 polygons each via QGIS)
2. Pseudo-label: run V6 on all 214 available tiles, manually verify confident
   predictions, add them as training data
3. Hard negative mining: collect V6 false positives, add as explicit background chips
