#!/bin/bash -l
#SBATCH --job-name=cpis_train
#SBATCH --output=%x_%j.log
#SBATCH --error=%x_%j.err
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=24:00:00

set -euo pipefail

cd /home/ermiller/global_cpis_codes

PYTHON_BIN="/home/ermiller/.conda/envs/cpi_fix/bin/python"
export PROJ_LIB="/home/ermiller/.conda/envs/cpi_fix/share/proj"
export PROJ_DATA="$PROJ_LIB"
DATASET_ROOT="${CPIS_DATASET_ROOT:-runs/new_method/rse2023_2015_v1/datasets/2015_ssa_stable_v2}"
CONFIG_PATH="${CPIS_CONFIG:-model/cascade_mask_rcnn_pointrend_cbam.py}"
TOTAL_EPOCHS="${CPIS_TOTAL_EPOCHS:-6}"
OPTIMIZER_LR="${CPIS_OPTIMIZER_LR:-0}"
GRAD_CLIP_MAX_NORM="${CPIS_GRAD_CLIP_MAX_NORM:-0}"
CHECKPOINT_PATH="${CPIS_CHECKPOINT:-}"
MODEL_TAG="${CPIS_MODEL_TAG:-2015_ssa_stable_v2_smoke}"
WORK_DIR="runs/new_method/rse2023_2015_v1/models/${MODEL_TAG}_${SLURM_JOB_ID}"
LOG_FILE="${WORK_DIR}/train_paper_model.log"
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing python interpreter: $PYTHON_BIN" >&2
  exit 1
fi

echo "Host: $(hostname)"
echo "Start: $(date)"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-<unset>}"
echo "Python: $PYTHON_BIN"
echo "PROJ_LIB: $PROJ_LIB"
echo "Work dir: $WORK_DIR"
echo "Dataset root: $DATASET_ROOT"
echo "Total epochs: $TOTAL_EPOCHS"
echo "Optimizer LR override: $OPTIMIZER_LR"
echo "Grad clip max norm: $GRAD_CLIP_MAX_NORM"
echo "Config: $CONFIG_PATH"
echo "Checkpoint override: ${CHECKPOINT_PATH:-<default>}"

nvidia-smi || true

TRAIN_ARGS=(
  tools/new_method/train_paper_model.py
  --dataset-root "$DATASET_ROOT" \
  --config "$CONFIG_PATH" \
  --work-dir "$WORK_DIR" \
  --log-file "$LOG_FILE" \
  --compute-stats \
  --validate \
  --total-epochs "$TOTAL_EPOCHS" \
  --optimizer-lr "$OPTIMIZER_LR" \
  --grad-clip-max-norm "$GRAD_CLIP_MAX_NORM" \
  --device cuda
)

if [[ -n "$CHECKPOINT_PATH" ]]; then
  TRAIN_ARGS+=(--checkpoint "$CHECKPOINT_PATH")
fi

"$PYTHON_BIN" "${TRAIN_ARGS[@]}"

echo "End: $(date)"
