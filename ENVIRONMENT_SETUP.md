# Environment Setup on HPC

Complete guide for recreating your Python environment on HPC clusters.

## Quick Comparison

| Method | Pros | Cons | Best For |
|--------|------|------|----------|
| **Conda Export** | Simple, fast | May have compatibility issues | Similar OS versions |
| **Requirements.txt** | Standard Python | Need to manage dependencies | Simple environments |
| **Singularity** | Perfect reproducibility | Requires container build | Complex environments |
| **HPC Modules** | Pre-installed, fast | Limited versions | Standard tools |

## Method 1: Conda Environment Export (Easiest)

### Step 1: Export Your Local Environment

```bash
# On your local machine
conda activate your_cpi_env  # or whatever your env is called

# Export full environment (platform-specific)
conda env export > environment.yml

# OR export only explicitly installed packages (better for cross-platform)
conda env export --from-history > environment_minimal.yml

# Also save pip packages
pip freeze > requirements.txt

# Save conda list for reference
conda list --export > conda_packages.txt
```

### Step 2: Transfer to HPC

```bash
# Copy to HPC
scp environment.yml requirements.txt username@hpc.edu:/home/username/global_cpis_codes/
```

### Step 3: Recreate on HPC

```bash
# SSH to HPC
ssh username@hpc.edu

# Load conda module (check what your HPC provides)
module avail conda  # See available conda modules
module load anaconda3  # or miniconda3, or python/anaconda

# Create environment
conda env create -f environment.yml -n cpi_detection

# OR if that fails due to platform differences:
conda create -n cpi_detection python=3.7
conda activate cpi_detection
pip install -r requirements.txt

# Verify installation
python -c "import torch; print(torch.__version__)"
python -c "import mmdet; print(mmdet.__version__)"
```

## Method 2: Manual Installation with HPC Modules

Most HPCs have pre-installed modules. Use them when possible:

### Step 1: Check Available Modules

```bash
# On HPC
module avail

# Common modules you need:
# - python (3.7)
# - cuda (10.1)
# - cudnn
# - gcc/g++
# - gdal
```

### Step 2: Load Modules and Install

```bash
# Load required modules
module load python/3.7
module load cuda/10.1
module load cudnn/7.6.5
module load gdal/3.2.0

# Create virtual environment
python -m venv ~/envs/cpi_detection
source ~/envs/cpi_detection/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install PyTorch (CUDA 10.1 version)
pip install torch==1.6.0+cu101 torchvision==0.7.0+cu101 -f https://download.pytorch.org/whl/torch_stable.html

# Install mmcv
pip install mmcv-full==1.2.4 -f https://download.openmmlab.com/mmcv/dist/cu101/torch1.6.0/index.html

# Install mmdet
pip install mmdet==2.7.0

# Install other dependencies
pip install earthengine-api
pip install gdal==3.2.0
pip install shapely==1.7.1
pip install geopandas
```

### Step 3: Create Activation Script

Create `~/load_cpi_env.sh`:

```bash
#!/bin/bash
# Load modules
module load python/3.7
module load cuda/10.1
module load cudnn/7.6.5
module load gdal/3.2.0

# Activate virtual environment
source ~/envs/cpi_detection/bin/activate

echo "CPI Detection environment loaded"
echo "Python: $(which python)"
echo "PyTorch: $(python -c 'import torch; print(torch.__version__)')"
```

Use it:
```bash
source ~/load_cpi_env.sh
```

## Method 3: Singularity Container (Most Reproducible)

Singularity is the standard container system for HPC (Docker usually not allowed).

### Step 1: Build Container Locally (if you have Singularity)

```bash
# On your local machine (with Singularity installed)
sudo singularity build cpi_detection.sif singularity.def

# Transfer to HPC
scp cpi_detection.sif username@hpc.edu:/home/username/
```

### Step 2: OR Build on HPC (if allowed)

```bash
# On HPC
singularity build cpi_detection.sif singularity.def
```

### Step 3: OR Convert from Docker (easiest)

```bash
# Pull and convert Docker image to Singularity
singularity pull docker://pytorch/pytorch:1.6.0-cuda10.1-cudnn7-devel

# This creates: pytorch_1.6.0-cuda10.1-cudnn7-devel.sif
```

### Step 4: Use Container

```bash
# Run detection with GPU
singularity exec --nv cpi_detection.sif python batch_detect_africa.py

# Interactive shell
singularity shell --nv cpi_detection.sif

# In SLURM script:
#!/bin/bash
#SBATCH --gres=gpu:1
#SBATCH --partition=gpu

singularity exec --nv /home/username/cpi_detection.sif \
    python /home/username/global_cpis_codes/batch_detect_africa.py
```

**Singularity flags:**
- `--nv`: Enable NVIDIA GPU support
- `-B /path:/path`: Bind mount directories
- `--cleanenv`: Clean environment variables

## Method 4: Use Existing HPC Environment

Some HPCs have ML environments pre-configured:

```bash
# Check for existing environments
module avail pytorch
module avail tensorflow
module avail ml

# Example - some HPCs have:
module load pytorch/1.6.0-cuda10.1

# Then just install missing packages:
pip install --user mmdet==2.7.0
pip install --user earthengine-api
```

## Troubleshooting

### Issue: "CUDA version mismatch"

```bash
# Check available CUDA
module avail cuda

# Load matching version
module load cuda/10.1

# Install matching PyTorch
pip install torch==1.6.0+cu101 -f https://download.pytorch.org/whl/torch_stable.html
```

### Issue: "No module named 'mmcv'"

```bash
# Install pre-built mmcv (faster than building)
pip install mmcv-full==1.2.4 -f https://download.openmmlab.com/mmcv/dist/cu101/torch1.6.0/index.html

# If that fails, check your PyTorch version:
python -c "import torch; print(torch.__version__)"
```

### Issue: "Permission denied" when pip install

```bash
# Use --user flag
pip install --user package_name

# Or use virtual environment
python -m venv ~/my_env
source ~/my_env/bin/activate
pip install package_name
```

### Issue: "ImportError: libgdal.so"

```bash
# Load gdal module
module load gdal

# Or set library path
export LD_LIBRARY_PATH=/path/to/gdal/lib:$LD_LIBRARY_PATH
```

### Issue: "MMDetection import error"

```bash
# Reinstall MMDetection
cd /path/to/mmdetection
pip install -v -e .

# Or install from source:
git clone https://github.com/open-mmlab/mmdetection.git
cd mmdetection
git checkout v2.7.0
pip install -r requirements/build.txt
pip install -v -e .
```

## Verification Script

Save as `test_environment.py`:

```python
"""Test if CPI detection environment is correctly set up."""

import sys

def test_import(module_name, package_name=None):
    """Test if a module can be imported."""
    package_name = package_name or module_name
    try:
        __import__(module_name)
        print(f"✓ {package_name}")
        return True
    except ImportError as e:
        print(f"✗ {package_name}: {e}")
        return False

print("Testing CPI Detection Environment")
print("=" * 50)

# Test Python version
print(f"Python: {sys.version}")

# Test core packages
modules = [
    ('torch', 'PyTorch'),
    ('torchvision', 'TorchVision'),
    ('mmcv', 'MMCV'),
    ('mmdet', 'MMDetection'),
    ('gdal', 'GDAL'),
    ('shapely', 'Shapely'),
    ('ee', 'Earth Engine'),
]

all_passed = True
for module, name in modules:
    if not test_import(module, name):
        all_passed = False

# Test CUDA
print("\n" + "=" * 50)
try:
    import torch
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA version: {torch.version.cuda}")
        print(f"GPU count: {torch.cuda.device_count()}")
        print(f"GPU name: {torch.cuda.get_device_name(0)}")
except:
    print("✗ CUDA check failed")
    all_passed = False

# Test versions
print("\n" + "=" * 50)
try:
    import torch
    print(f"PyTorch version: {torch.__version__}")
    import mmdet
    print(f"MMDetection version: {mmdet.__version__}")
    import mmcv
    print(f"MMCV version: {mmcv.__version__}")
except:
    pass

print("\n" + "=" * 50)
if all_passed:
    print("✓ All tests passed!")
else:
    print("✗ Some tests failed - check installation")
```

Run it:
```bash
python test_environment.py
```

## Project-Specific Setup

After environment is ready, set up the project:

```bash
# Navigate to project
cd ~/global_cpis_codes

# Extract model (one-time)
cd model
unrar x cascade_mask_rcnn_pointrend_cbam.part1.rar
ln -s epoch_140.pth cascade_mask_rcnn_pointrend_cbam.pth
cd ..

# Test on sample images
python demo.py

# If successful, you're ready for Africa-scale processing!
```

## Recommended Approach by HPC Type

**If your HPC has:**

- **Conda available** → Use Method 1 (conda export)
- **Good module system** → Use Method 2 (modules + pip)
- **Singularity support** → Use Method 3 (container)
- **None of above** → Use Method 2 with manual installation

## Quick Reference

```bash
# === CONDA APPROACH ===
# Local
conda env export > environment.yml

# HPC
module load anaconda3
conda env create -f environment.yml -n cpi_detection
conda activate cpi_detection

# === MODULE APPROACH ===
module load python/3.7 cuda/10.1 gdal
python -m venv ~/envs/cpi_detection
source ~/envs/cpi_detection/bin/activate
pip install -r requirements.txt

# === CONTAINER APPROACH ===
singularity pull docker://pytorch/pytorch:1.6.0-cuda10.1-cudnn7-devel
singularity exec --nv pytorch_*.sif python batch_detect_africa.py
```

## Getting Help

**Contact your HPC support:**
- Ask about available Python/CUDA modules
- Ask about Singularity availability
- Ask about recommended ML workflows

**Check HPC documentation:**
- Most HPCs have ML/PyTorch setup guides
- Look for "GPU computing" or "Machine Learning" sections

Good luck with your setup! 🚀
