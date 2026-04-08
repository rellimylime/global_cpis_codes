#!/bin/bash -l
#SBATCH --job-name=cpis_infer
#SBATCH --output=%x_%j.log
#SBATCH --error=%x_%j.err
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00

set -euo pipefail

cd /home/ermiller/global_cpis_codes

PYTHON_BIN="/home/ermiller/.conda/envs/cpi_fix/bin/python"
export PROJ_LIB="/home/ermiller/.conda/envs/cpi_fix/share/proj"
export PROJ_DATA="$PROJ_LIB"

IMAGERY_DIR="${CPIS_INFER_IMAGERY:-runs/new_method/rse2023_2015_v1/active_label_v1/input_tiles}"
OUT_ROOT="${CPIS_INFER_OUT:-runs/new_method/rse2023_2015_v1/active_label_v1/inference}"
CONFIG="${CPIS_INFER_CONFIG:-runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v6_177071/resolved_config.py}"
CHECKPOINT="${CPIS_INFER_CHECKPOINT:-runs/new_method/rse2023_2015_v1/models/2015_ssa_stable_v6_177071/best_segm_mAP_epoch_17.pth}"
SCORE_THR="${CPIS_INFER_SCORE_THR:-0.3}"

echo "Host: $(hostname)"
echo "Start: $(date)"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-<unset>}"
echo "Imagery: $IMAGERY_DIR"
echo "Output:  $OUT_ROOT"
echo "Config:  $CONFIG"
echo "Checkpoint: $CHECKPOINT"
echo "Score thr: $SCORE_THR"

nvidia-smi || true

"$PYTHON_BIN" tools/new_method/run_paper_inference.py \
  --imagery-dir "$IMAGERY_DIR" \
  --out-root    "$OUT_ROOT" \
  --config      "$CONFIG" \
  --checkpoint  "$CHECKPOINT" \
  --score-thr   "$SCORE_THR"

echo "End: $(date)"
