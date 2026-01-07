#!/bin/bash
#SBATCH --job-name=cpi_cpu
#SBATCH --output=cpi_pipeline_%j.log
#SBATCH --error=cpi_pipeline_%j.err
#SBATCH --time=72:00:00
#SBATCH --mem=128G
#SBATCH --cpus-per-task=16
#SBATCH --partition=grit_nodes

source ~/.bashrc
conda activate cpi_detection2

# FORCE CPU MODE - disable CUDA
export CUDA_VISIBLE_DEVICES=""

echo "=== Running on CPU (CUDA disabled) ==="
echo ""

cd /home/waves/data/global_cpis_codes-1

# Loop until complete
while true; do
    echo "=== Pipeline iteration at $(date) ==="
    python pipeline_master.py
    
    # Check if we're done
    if python -c "
import json
with open('pipeline_state.json', 'r') as f:
    state = json.load(f)
arid = set(state['arid_tiles'])
processed = set(state['processed_tiles'])
failed = set(state['failed_tiles'])
remaining = len(arid - processed - failed)
print(f'Remaining: {remaining}')
exit(0 if remaining == 0 else 1)
    "; then
        echo "=== COMPLETE at $(date) ==="
        break
    fi
    
    # Only wait if GDrive is empty (need to wait for exports)
    tiles_in_gdrive=$(python -c "
import json
with open('pipeline_state.json', 'r') as f:
    state = json.load(f)
print(len(state['in_gdrive']))
")
    
    if [ "$tiles_in_gdrive" -eq 0 ]; then
        echo "=== No tiles in GDrive - waiting 30min for GEE exports ==="
        sleep 1800
    else
        echo "=== $tiles_in_gdrive tiles ready - continuing immediately ==="
        sleep 10
    fi
done

echo "=== Finished at $(date) ==="
