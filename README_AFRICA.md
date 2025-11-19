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

### Step 3: Download Tiles from Google Drive

As tiles finish exporting:

1. Go to your Google Drive → `Africa_CPI_Sentinel2/` folder
2. Download completed .tif files
3. Move them to the `imgs/` directory:

```bash
mv ~/Downloads/africa_s2_2021_tile_*.tif imgs/
```

**Tip:** You don't need to wait for all tiles! Download and process in batches.

### Step 4: Run CPI Detection

```bash
# Process all images in imgs/
python batch_detect_africa.py
```

This will:
- Load the CPI detection model
- Process each image (~2-5 min per image on GPU, ~1-2 hours on CPU)
- Save results to `result_africa/` directory

Each result includes:
- Detected CPI polygons
- Confidence scores
- Geospatial files (shapefiles/GeoJSON)

### Step 5: Process More Tiles

Download more tiles from Google Drive and repeat:

```bash
# Download more from Google Drive
mv ~/Downloads/africa_s2_2021_tile_*.tif imgs/

# Detect CPIs
python batch_detect_africa.py
```

The batch script skips already-processed images automatically.

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

## File Organization

```
global_cpis_codes/
├── imgs/                              # Downloaded Sentinel-2 tiles go here
│   ├── africa_s2_2021_tile_0001.tif
│   ├── africa_s2_2021_tile_0002.tif
│   └── ...
├── result_africa/                     # Detection results
│   ├── africa_s2_2021_tile_0001/
│   ├── africa_s2_2021_tile_0002/
│   └── ...
├── download_africa_gee.py             # Download script
├── batch_detect_africa.py             # Detection script
└── africa_tiles_2021_metadata.json    # Tile metadata
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
