#!/bin/bash
# Smart environment creator - detects platform and uses appropriate method

set -e

echo "=========================================="
echo "CPI Detection Environment Setup"
echo "=========================================="

# Detect platform
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PLATFORM="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    PLATFORM="macos"
else
    PLATFORM="unknown"
fi

echo "Detected platform: $PLATFORM"

# Detect if on HPC (common indicators)
IS_HPC=false
if [[ -d "/scratch" ]] || [[ -d "/gpfs" ]] || [[ -n "$SLURM_JOB_ID" ]] || command -v sbatch &> /dev/null; then
    IS_HPC=true
    echo "HPC environment detected"
fi

# Choose environment file
if [ -f "environment-${PLATFORM}.yml" ]; then
    ENV_FILE="environment-${PLATFORM}.yml"
    echo "Using platform-specific: $ENV_FILE"
elif [ -f "environment-minimal.yml" ]; then
    ENV_FILE="environment-minimal.yml"
    echo "Using minimal environment: $ENV_FILE"
elif [ -f "environment.yml" ]; then
    ENV_FILE="environment.yml"
    echo "Using environment.yml"
else
    echo "No environment file found. Creating from requirements.txt"
    ENV_FILE="none"
fi

# Check if conda available
if ! command -v conda &> /dev/null; then
    echo "Error: conda not found"
    echo ""
    echo "Options:"
    echo "1. Load conda module: module load anaconda3"
    echo "2. Install miniconda: https://docs.conda.io/en/latest/miniconda.html"
    echo "3. Use pip with: pip install -r requirements.txt"
    exit 1
fi

# Create environment
ENV_NAME="cpi_detection"

if conda env list | grep -q "^${ENV_NAME} "; then
    echo ""
    echo "Environment '$ENV_NAME' already exists"
    read -p "Remove and recreate? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        conda env remove -n $ENV_NAME
    else
        echo "Keeping existing environment"
        exit 0
    fi
fi

if [ "$ENV_FILE" != "none" ]; then
    echo ""
    echo "Creating environment from $ENV_FILE..."
    conda env create -f $ENV_FILE
else
    echo ""
    echo "Creating environment from scratch..."
    conda create -n $ENV_NAME python=3.7 -y
    conda activate $ENV_NAME

    # Install PyTorch with CUDA
    conda install pytorch=1.6.0 torchvision=0.7.0 cudatoolkit=10.1 -c pytorch -y

    # Install from requirements.txt
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
    fi
fi

echo ""
echo "=========================================="
echo "✓ Environment created successfully!"
echo "=========================================="
echo ""
echo "Activate with:"
echo "  conda activate $ENV_NAME"
echo ""

if $IS_HPC; then
    echo "Next steps for HPC:"
    echo "1. Authenticate Earth Engine:"
    echo "   earthengine authenticate"
    echo ""
    echo "2. Setup rclone for Google Drive:"
    echo "   rclone config"
    echo ""
    echo "3. Configure HPC paths:"
    echo "   python hpc_config.py"
fi

echo "Test installation:"
echo "  python -c 'import torch; print(torch.__version__)'"
echo "  python demo.py"
