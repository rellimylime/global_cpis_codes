#!/bin/bash -l
#SBATCH --job-name=cpis_gold_eval
#SBATCH --output=%x_%j.log
#SBATCH --error=%x_%j.err
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=08:00:00

set -euo pipefail

cd /home/ermiller/global_cpis_codes

PYTHON_BIN="/home/ermiller/.conda/envs/cpi_fix/bin/python"
export PROJ_LIB="/home/ermiller/.conda/envs/cpi_fix/share/proj"
export PROJ_DATA="$PROJ_LIB"

DATASET_ROOT="${CPIS_GOLD_DATASET_ROOT:-runs/new_method/rse2023_2015_v1/gold_eval/2015_gold_val_v1/dataset}"
CONFIG_PATH="${CPIS_GOLD_CONFIG:-runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v3_from_2021_174031/resolved_config.py}"
CHECKPOINT_PATH="${CPIS_GOLD_CHECKPOINT:-runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v3_from_2021_174031/best_segm_mAP_epoch_19.pth}"
OUT_TAG="${CPIS_GOLD_OUT_TAG:-2015_gold_val_eval}"
OUT_ROOT="runs/new_method/rse2023_2015_v1/gold_eval_runs/${OUT_TAG}_${SLURM_JOB_ID}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing python interpreter: $PYTHON_BIN" >&2
  exit 1
fi

echo "Host: $(hostname)"
echo "Start: $(date)"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-<unset>}"
echo "Python: $PYTHON_BIN"
echo "PROJ_LIB: $PROJ_LIB"
echo "Gold dataset: $DATASET_ROOT"
echo "Config: $CONFIG_PATH"
echo "Checkpoint: $CHECKPOINT_PATH"
echo "Output root: $OUT_ROOT"

nvidia-smi || true

"$PYTHON_BIN" tools/new_method/run_gold_eval.py \
  --dataset-root "$DATASET_ROOT" \
  --config "$CONFIG_PATH" \
  --checkpoint "$CHECKPOINT_PATH" \
  --out-root "$OUT_ROOT"

echo "End: $(date)"
