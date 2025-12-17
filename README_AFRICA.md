# CPI Detection for All of Africa - Quick Start

This guide shows you how to detect Central Pivot Irrigation Systems across all of Africa using Sentinel-2 imagery from 2021.

## Overview

**Workflow:**
1. Download Sentinel-2 data for Africa using Google Earth Engine (automated, chunk by chunk)
2. Process downloaded tiles through the CPI detection model (batch processing)
3. Collect and analyze results

**Time:** 1-2 weeks total (mostly waiting for exports)
**Storage:** ~200-500 GB for processed tiles
**GPU:** Recommended (100x faster detection)

## Step-by-Step Guide

### Step 1: Setup Google Earth Engine (One-time, 10 minutes)

```bash
# Install Earth Engine
pip install earthengine-api

# Authenticate (opens browser for Google login)
earthengine authenticate
```

Follow the prompts to authenticate with your Google account.

### Step 2: Download Sentinel-2 Data for Africa

```bash
# Edit download_africa_gee.py if you want to customize:
# - GRID_SIZE (default 2.0° = ~222km tiles)
# - MAX_CLOUD_COVER (default 30%)
# - MAX_EXPORTS_PER_RUN (default 50 tiles per run)

# Start exports
python download_africa_gee.py
```

This will:
- Create a grid covering all of Africa (~800-1000 tiles)
- Generate cloud-free annual composites for each tile
- Export to your Google Drive folder: `Africa_CPI_Sentinel2/`

**The script will start exports and exit - exports continue on Google's servers.**

Monitor progress: https://code.earthengine.google.com/tasks

### Step 3: Download and Track Tiles

**Systematic Processing (Recommended):**

Use the tracking script to process tiles in batches:

```bash
# Check what needs processing (use your Google Drive folder path)
python process_africa_tiles.py --source ~/Downloads/Africa_CPI_Sentinel2 --dry-run

# Move next batch (e.g., 10 tiles) to imgs/
python process_africa_tiles.py --source ~/Downloads/Africa_CPI_Sentinel2 --batch-size 10
```

This script:
- Tracks which tiles have been processed
- Moves unprocessed tiles to `imgs/` in batches
- Shows progress: "64/1000 (6.4%)"
- Never loses track of what's done

**Or Manual Method:**

```bash
# Download from Google Drive and move to imgs/
mv ~/Downloads/africa_s2_2021_tile_*.tif imgs/
```

### Step 4: Run CPI Detection

```bash
# Process all images in imgs/
python batch_detect_africa.py
```

This will:
- Load the CPI detection model
- Process each image (~2-5 min per image on GPU, ~1-2 hours on CPU)
- Save results to `result_africa/[tile_name]/`
- Skip already-processed tiles

Each result folder includes:
- Detected CPI polygons (shapefiles)
- Confidence scores
- Geospatial metadata

### Step 5: Export and Process Next Batch

**Continue until all of Africa is complete:**

```bash
# Export next 50 tiles from GEE (automatically resumes)
python download_africa_gee.py

# Wait for exports, then download and process
python process_africa_tiles.py --source ~/Downloads/Africa_CPI_Sentinel2
python batch_detect_africa.py

# Repeat ~15-20 times for all ~1000 tiles
```

### Step 6: Merge All Results

Once you've processed many tiles, merge into one Africa-wide shapefile:

```bash
python merge_africa_results.py
```

**Output:**
- `africa_cpis_2021.shp` - Single shapefile with ALL detected CPIs
- `africa_cpis_2021_summary.json` - Statistics (total CPIs, area, coverage)
- Includes attributes: tile_id, confidence, area_ha

You can run this anytime to merge all results processed so far.

## Configuration Options

### Smaller Test Area

Edit `download_africa_gee.py` line 27 to test on a smaller region:

```python
# East Africa only
AFRICA_BBOX = [20.0, -12.0, 52.0, 18.0]

# North Africa
AFRICA_BBOX = [-17.0, 15.0, 51.0, 37.0]

# Sahel region
AFRICA_BBOX = [-17.0, 10.0, 40.0, 20.0]
```

### Adjust Tile Size

Smaller tiles = smaller files but more exports:

```python
GRID_SIZE = 1.0  # ~111km tiles (smaller, more tiles)
GRID_SIZE = 3.0  # ~333km tiles (larger, fewer tiles)
```

### Adjust Detection Sensitivity

Edit `batch_detect_africa.py` line 24:

```python
score_thr=[0.3, 0.85],  # Lower threshold = more detections (may include false positives)
score_thr=[0.5, 0.90],  # Higher threshold = fewer detections (more confident)
```

## Resource Requirements

**For all of Africa (~1000 tiles):**

- **Storage**: 300-600 GB (processed tiles + results)
- **RAM**: 16 GB recommended
- **GPU**: Highly recommended
  - With GPU: 2-3 seconds per tile
  - Without GPU: 2-5 minutes per tile
- **Total processing time**:
  - With GPU: 1-2 hours per 100 tiles
  - Without GPU: 3-8 hours per 100 tiles

**Google Earth Engine exports:**
- Free tier: Unlimited exports
- Time: 10-30 minutes per tile
- Total: 1-3 days for all tiles

## Troubleshooting

**"Earth Engine not authenticated"**
```bash
earthengine authenticate
```

**"No images found" for some tiles**
- Normal for very cloudy regions
- Tiles will be skipped automatically
- Check MAX_CLOUD_COVER setting

**"Out of memory" during detection**
- Process fewer images at once
- Close other applications
- Consider using smaller tiles

**Google Drive storage full**
- Process and delete tiles incrementally
- Don't need to keep all tiles at once

**Exports stuck as "RUNNING"**
- Normal - GEE can take hours per tile
- Check back later
- Exports continue even if you close browser

## Progress Tracking

The workflow automatically tracks your progress:

**Export Progress:**
- `gee_export_progress.json` - Which tiles have been exported from GEE
- Shows: 64/1000 tiles exported (6.4%)
- `download_africa_gee.py` automatically resumes from last export

**Processing Progress:**
- `africa_processing_progress.json` - Which tiles have been processed
- Tracks: processed, in_progress, remaining tiles
- `process_africa_tiles.py` uses this to avoid reprocessing

**Check Progress:**
```bash
# See export progress
cat gee_export_progress.json | grep total_exported

# See processing progress
cat africa_processing_progress.json | grep -E "processed|total"

# Count processed results
ls result_africa/ | wc -l
```

## File Organization

```
global_cpis_codes/
├── imgs/                                   # Current batch (10-20 tiles)
│   ├── africa_s2_2021_tile_0042.tif
│   └── ...
├── result_africa/                          # Detection results
│   ├── africa_s2_2021_tile_0042/          # Per-tile results
│   │   ├── cpis.shp                       # Detected CPIs (shapefile)
│   │   └── ...
│   └── ...
├── africa_cpis_2021.shp                   # FINAL MERGED SHAPEFILE
├── africa_cpis_2021_summary.json          # Statistics
├── gee_export_progress.json               # Export tracking
├── africa_processing_progress.json        # Processing tracking
└── Scripts:
    ├── download_africa_gee.py             # Export tiles from GEE
    ├── process_africa_tiles.py            # Move tiles in batches
    ├── batch_detect_africa.py             # Run detection
    └── merge_africa_results.py            # Merge into one shapefile
```

## Tips for Large-Scale Processing

1. **Start small**: Test on 5-10 tiles first to verify everything works

2. **Process incrementally**: Download 50 tiles → Process → Delete → Repeat

3. **Use GPU**: Rent a cloud GPU instance if you don't have one (much faster)

4. **Monitor disk space**: Each tile is ~300-500 MB, results are ~50-100 MB

5. **Keep metadata**: The `africa_tiles_2021_metadata.json` file tracks which tiles were exported

6. **Resume anytime**: Both download and detection can be stopped and resumed

## Support

Check the main README.md for:
- Model installation requirements
- Dependencies (CUDA, PyTorch, MMDetection)
- Additional documentation

## Quick Reference

```bash
# Setup (once)
pip install earthengine-api
earthengine authenticate

# Download tiles
python download_africa_gee.py

# Check GEE tasks
# https://code.earthengine.google.com/tasks

# Download from Drive → move to imgs/
mv ~/Downloads/africa_s2_*.tif imgs/

# Detect CPIs
python batch_detect_africa.py

# Results in result_africa/
ls result_africa/
```

Start processing today - you'll have Africa covered in 1-2 weeks!
