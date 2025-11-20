# Running CPI Detection on HPC

Complete guide for running the Africa-wide CPI detection on High Performance Computing clusters.

## Why Use HPC?

- **GPU access**: Faster detection (2-3 sec/tile vs 2-5 min/tile on CPU)
- **Storage**: Terabytes for all tiles
- **Processing power**: Run 24/7 without interruption
- **Parallel processing**: Process multiple tiles simultaneously

## Important: How GEE Works with HPC

**GEE does NOT save files to HPC directly!**

The workflow is:
1. **HPC** → Run export script → Tell GEE what to process
2. **GEE** → Process on Google's servers → Save to YOUR Google Drive
3. **YOU** → Download from Google Drive → HPC storage
4. **HPC** → Run detection on downloaded tiles

## One-Time Setup

### 1. Install Dependencies on HPC

```bash
# Load modules (adjust for your HPC)
module load python/3.7
module load cuda/10.1
module load gdal

# Install Python packages
pip install --user earthengine-api
pip install --user rclone  # for Google Drive downloads

# Install MMDetection and other requirements
# (Follow main README.md installation instructions)
```

### 2. Authenticate Google Earth Engine

```bash
# Run authentication
earthengine authenticate
```

**This will:**
1. Print a URL
2. Open URL in browser (on your laptop, not HPC)
3. Login with Google account
4. Copy authorization code
5. Paste code back in HPC terminal

**Authentication is saved in:** `~/.config/earthengine/credentials`

**Re-authentication needed when:**
- Working on different HPC cluster
- Token expires (usually doesn't)
- Different user account

### 3. Setup rclone for Google Drive

```bash
# Configure rclone
rclone config

# When prompted:
n  # New remote
gdrive  # Name it
<drive_number>  # Select Google Drive type
<enter>  # Client ID (blank = default)
<enter>  # Client secret (blank = default)
1  # Scope: Full access
n  # Advanced config? No
n  # Auto config? No (you're on HPC)

# You'll get a URL - open in browser
# Authorize and copy verification code
# Paste code back in terminal

# Test it works
rclone ls gdrive:
```

### 4. Configure Paths for HPC

Edit `hpc_config.py`:

```python
# Use /scratch or fast storage, NOT home directory
TILE_STORAGE = '/scratch/your_username/africa_tiles'
RESULT_STORAGE = '/scratch/your_username/cpi_results'
TEMP_STORAGE = '/scratch/your_username/temp'
```

Create directories:
```bash
python hpc_config.py
```

## Regular Workflow

### Step 1: Export Tiles from GEE

```bash
# On HPC - this just queues tasks, runs quickly
python download_africa_gee.py
```

**What this does:**
- Creates export tasks on GEE
- Tasks run on Google's servers (not HPC)
- Results go to YOUR Google Drive
- Script exits immediately

**Monitor tasks:**
- Visit: https://code.earthengine.google.com/tasks
- Check status: READY → RUNNING → COMPLETED

### Step 2: Download Tiles from Google Drive to HPC

**Option A: Using rclone (Recommended)**

```bash
# Download all tiles from Google Drive
rclone copy gdrive:Africa_CPI_Sentinel2 /scratch/username/africa_tiles/ --progress

# Or sync (only downloads new files)
rclone sync gdrive:Africa_CPI_Sentinel2 /scratch/username/africa_tiles/ --progress
```

**Option B: Manual Download + Transfer**

```bash
# On your laptop:
# 1. Download from Google Drive to ~/Downloads/
# 2. Transfer to HPC:
scp -r ~/Downloads/Africa_CPI_Sentinel2/*.tif username@hpc:/scratch/username/africa_tiles/

# Or use rsync for resume capability:
rsync -avz --progress ~/Downloads/Africa_CPI_Sentinel2/ username@hpc:/scratch/username/africa_tiles/
```

### Step 3: Process Tiles on HPC

```bash
# Process in batches
python process_africa_tiles.py --source /scratch/username/africa_tiles --batch-size 20

# Run detection
python batch_detect_africa.py
```

**For GPU job on HPC:**

Create SLURM script `detect_cpis.slurm`:

```bash
#!/bin/bash
#SBATCH --job-name=cpi_detect
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --time=24:00:00
#SBATCH --mem=32G
#SBATCH --output=cpi_detect_%j.log

# Load modules
module load python/3.7
module load cuda/10.1

# Activate environment if needed
# source activate myenv

# Run detection
cd /home/username/global_cpis_codes
python batch_detect_africa.py
```

Submit job:
```bash
sbatch detect_cpis.slurm
```

Monitor:
```bash
squeue -u username
tail -f cpi_detect_*.log
```

### Step 4: Merge Results

```bash
python merge_africa_results.py
```

### Step 5: Export Next Batch

```bash
# Export next 50 tiles
python download_africa_gee.py
```

Repeat steps 2-5 until all of Africa is done!

## Optimized HPC Workflow

### Parallel Processing

Process multiple batches in parallel with SLURM job arrays:

Create `detect_array.slurm`:

```bash
#!/bin/bash
#SBATCH --job-name=cpi_array
#SBATCH --array=1-10  # 10 parallel jobs
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --time=12:00:00
#SBATCH --mem=32G

# Each job processes different tiles
BATCH_SIZE=10
START=$((($SLURM_ARRAY_TASK_ID - 1) * $BATCH_SIZE))

python process_and_detect.py --start $START --count $BATCH_SIZE
```

### Automated Pipeline

Create `pipeline.sh` to automate everything:

```bash
#!/bin/bash

# 1. Export from GEE
python download_africa_gee.py

# 2. Wait for exports (check every hour)
while [ $(rclone lsf gdrive:Africa_CPI_Sentinel2 | wc -l) -lt 50 ]; do
    echo "Waiting for GEE exports..."
    sleep 3600  # 1 hour
done

# 3. Download tiles
rclone sync gdrive:Africa_CPI_Sentinel2 /scratch/username/africa_tiles/

# 4. Process tiles
python process_africa_tiles.py --source /scratch/username/africa_tiles
sbatch detect_cpis.slurm

# 5. Wait for detection to finish
# Then loop back to step 1
```

## Storage Management

**Disk space considerations:**

- **Per tile**: ~500 MB
- **50 tiles**: ~25 GB
- **1000 tiles (all Africa)**: ~500 GB
- **Results**: ~50-100 MB per tile

**Strategies:**

1. **Process in batches**: Download 50 → Process → Delete → Repeat
2. **Use scratch space**: Don't use home directory (often has quotas)
3. **Clean up**: Delete source tiles after processing (keep results)

```bash
# Check disk usage
du -sh /scratch/username/africa_tiles/
du -sh result_africa/

# Clean up processed tiles
rm /scratch/username/africa_tiles/africa_s2_*.tif
```

## Authentication Details

### Where credentials are stored:

**Earth Engine:**
- Location: `~/.config/earthengine/credentials`
- Persists across sessions
- One authentication per HPC account

**rclone:**
- Location: `~/.config/rclone/rclone.conf`
- Persists across sessions
- One configuration per HPC account

### When to re-authenticate:

**GEE - Rarely needed:**
- First time on new HPC
- If you see "Please authenticate" errors
- Token typically lasts indefinitely

**rclone - Rarely needed:**
- First time on new HPC
- If you see authentication errors
- Token refreshes automatically

### Multiple users sharing HPC:

Each user needs their own authentication:
- Each gets their own `~/.config/` directory
- Each authenticates with their own Google account
- Exports go to their respective Google Drives

## Troubleshooting

**"Please authenticate earthengine"**
```bash
earthengine authenticate
```

**"rclone: not authorized"**
```bash
rclone config reconnect gdrive:
```

**"No space left on device"**
```bash
# Use different storage location
export TMPDIR=/scratch/username/temp
# Or clean up old tiles
```

**"CUDA out of memory"**
```bash
# Reduce batch size in detection script
# Or request more GPU memory in SLURM
```

**"Cannot find tiles"**
```bash
# Check rclone downloaded correctly
rclone ls gdrive:Africa_CPI_Sentinel2
ls /scratch/username/africa_tiles/
```

## Summary of Key Points

✅ **GEE exports to YOUR Google Drive** (not to HPC directly)

✅ **Authentication is one-time per HPC** (credentials saved)

✅ **Use rclone to download** from Google Drive to HPC

✅ **Exports go to same Google Drive** regardless of where you run script

✅ **Process on HPC with GPU** for 100x speedup

✅ **Batch processing** to manage storage

## Quick Reference

```bash
# === ONE-TIME SETUP ===
earthengine authenticate
rclone config  # Name it "gdrive"
python hpc_config.py  # Create directories

# === REGULAR WORKFLOW ===
# 1. Export tiles
python download_africa_gee.py

# 2. Download from Drive
rclone sync gdrive:Africa_CPI_Sentinel2 /scratch/username/africa_tiles/

# 3. Process tiles
python process_africa_tiles.py --source /scratch/username/africa_tiles
sbatch detect_cpis.slurm

# 4. Merge results
python merge_africa_results.py

# 5. Repeat for next batch
python download_africa_gee.py
```

Good luck with your HPC processing! 🚀
