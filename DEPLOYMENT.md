# Deployment Guide: Local vs HPC

This project works on both local machines and HPC clusters. Here's how to deploy to each.

## Platform-Specific Files

The repo includes environment files for different platforms:

- **`environment-linux.yml`** - For Linux HPC clusters
- **`environment-minimal.yml`** - Cross-platform (Mac/Windows/Linux)
- **`requirements.txt`** - Platform-agnostic pip packages
- **`create_environment.sh`** - Auto-detects platform and sets up environment

## Deployment Options

### Option 1: Local Machine (Mac/Windows/Linux)

**Clone and setup:**

```bash
# Clone repository
git clone <your-repo-url>
cd global_cpis_codes

# Create environment (auto-detects your platform)
bash create_environment.sh

# Or manually:
conda env create -f environment-minimal.yml

# Activate
conda activate cpi_detection

# Extract model
cd model && unrar x cascade_mask_rcnn_pointrend_cbam.part1.rar && cd ..

# Test
python demo.py
```

### Option 2: Linux HPC Cluster

**Transfer to HPC:**

```bash
# From your local machine
git clone <your-repo-url>
cd global_cpis_codes

# Transfer to HPC (replace with your HPC details)
rsync -avz --exclude='.git' ./ username@hpc.edu:/home/username/global_cpis_codes/
```

**Setup on HPC:**

```bash
# SSH to HPC
ssh username@hpc.edu
cd ~/global_cpis_codes

# Run automated setup
bash setup_hpc.sh

# Or create environment manually:
bash create_environment.sh  # Auto-detects HPC and uses environment-linux.yml

# Activate
conda activate cpi_detection

# Configure HPC paths
python hpc_config.py
```

### Option 3: Using Singularity Container (HPC)

**Best for complex HPC environments:**

```bash
# On HPC (or build locally and transfer)
singularity build cpi_detection.sif singularity.def

# Use container
singularity exec --nv cpi_detection.sif python batch_detect_africa.py
```

## Key Differences: Local vs HPC

### Local Machine:
- **Storage**: Use local disk (`~/Downloads/`, etc.)
- **Processing**: Single machine, may be slow without GPU
- **Google Drive**: Manual download via browser
- **Use case**: Testing, small regions

### HPC:
- **Storage**: Use `/scratch` or `/gpfs` (high-performance storage)
- **Processing**: GPU nodes, batch jobs with SLURM
- **Google Drive**: Use `rclone` for automated downloads
- **Use case**: All of Africa, production runs

## Configuration Files

### `hpc_config.py` - HPC-specific paths

Edit this for your HPC:

```python
TILE_STORAGE = '/scratch/username/africa_tiles'     # HPC storage
RESULT_STORAGE = '/scratch/username/cpi_results'    # HPC storage
```

### Scripts automatically detect environment:

- **`create_environment.sh`** - Detects HPC vs local
- **`setup_hpc.sh`** - Full HPC setup wizard
- **`process_africa_tiles.py`** - Uses paths from hpc_config.py

## Workflow Comparison

### Local Workflow:

```bash
# 1. Export tiles
python download_africa_gee.py

# 2. Download from Google Drive (manually via browser)
# Files go to: ~/Downloads/Africa_CPI_Sentinel2/

# 3. Process
python process_africa_tiles.py --source ~/Downloads/Africa_CPI_Sentinel2
python batch_detect_africa.py

# 4. Merge
python merge_africa_results.py
```

### HPC Workflow:

```bash
# 1. Load environment
source ~/load_cpi_env.sh

# 2. Export tiles
python download_africa_gee.py

# 3. Download via rclone (automated)
rclone sync gdrive:Africa_CPI_Sentinel2 /scratch/username/africa_tiles/

# 4. Submit batch job
sbatch detect_cpis.slurm

# 5. Merge results
python merge_africa_results.py
```

## Same Branch, Different Configs

**You don't need separate branches!** The same code works everywhere:

✅ **One branch** (`claude/main-012djo7qjrDGukmKETntxY2L`)
✅ **Platform-specific environment files** (auto-selected)
✅ **Configuration files** (hpc_config.py for HPC paths)
✅ **Smart scripts** (detect and adapt to environment)

## Syncing Between Local and HPC

**To update HPC with local changes:**

```bash
# On local machine
git push origin claude/main-012djo7qjrDGukmKETntxY2L

# On HPC
cd ~/global_cpis_codes
git pull origin claude/main-012djo7qjrDGukmKETntxY2L
```

**Or use rsync for quick sync:**

```bash
# From local to HPC
rsync -avz --exclude='.git' --exclude='imgs/*' --exclude='result*' \
    ./ username@hpc.edu:/home/username/global_cpis_codes/
```

## Environment File Details

### environment-linux.yml
- Full specification for Linux
- Includes all dependencies with versions
- Use on HPC clusters

### environment-minimal.yml
- Cross-platform compatible
- Conda resolves dependencies for your OS
- Use on Mac/Windows/Linux

### requirements.txt
- Platform-agnostic pip packages
- Fallback if conda not available
- Use with virtual environments

## Troubleshooting

**"Conda packages not compatible"**
- Use `environment-minimal.yml` instead of platform-specific
- Or use `requirements.txt` with pip

**"Different CUDA version on HPC"**
- Check available CUDA: `module avail cuda`
- Update environment file to match
- Or use Singularity container

**"Path differences between local and HPC"**
- Local: Use relative paths (`imgs/`, `result_africa/`)
- HPC: Edit `hpc_config.py` for absolute paths

**"Git conflicts when syncing"**
- HPC modifies: `hpc_config.py`, `gee_export_progress.json`
- Local modifies: Scripts and docs
- Add to `.gitignore` if needed

## Best Practice

1. **Develop locally** - Test scripts on sample data
2. **Commit changes** - Push to branch
3. **Pull on HPC** - Get latest code
4. **Run at scale** - Process all of Africa on HPC
5. **Pull results** - Download final shapefiles to local

## Quick Reference

```bash
# === SETUP (one-time) ===
# Local
bash create_environment.sh

# HPC
bash setup_hpc.sh

# === DAILY WORKFLOW ===
# Local: Quick tests
conda activate cpi_detection
python demo.py

# HPC: Production runs
source ~/load_cpi_env.sh
sbatch detect_cpis.slurm

# === SYNC ===
# Code: Git push/pull
# Data: rsync or rclone
```

No need for branches or forks - smart configuration handles everything! 🚀
