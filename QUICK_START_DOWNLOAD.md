# Quick Start: Download Sentinel-2 Data for 2021

## Problem You're Having

- The `sentinelsat` library doesn't work anymore (403 Forbidden error)
- Copernicus changed their API in 2024
- ArcGIS only offers PNG exports

## ✅ EASIEST SOLUTION: Manual Download (5 minutes)

No coding, no API credentials needed!

### Step 1: Go to Copernicus Browser
**https://browser.dataspace.copernicus.eu/**

### Step 2: Find Your Area
1. **Zoom in** to a specific region (NOT all of Africa!)
   - Example: Pick one province or ~100km x 100km area
   - Your ArcGIS coordinates: 0.94°N, 16.71°E (Central Africa)

2. **Draw a box** around your area:
   - Click the **polygon tool** (square icon in top-left toolbar)
   - Click 4 corners to draw a box
   - Double-click to finish

### Step 3: Filter Results
Click the **search settings** (gear icon on left panel):

1. **Time Range**:
   - Start: `2021-06-01`
   - End: `2021-08-31`
   - (Start with 3 months, expand if needed)

2. **Data Collections**:
   - Select: **Sentinel-2** → **L2A**

3. **Advanced Filters** (click "Show advanced"):
   - Cloud coverage: `0` to `20`

4. Click **SEARCH**

### Step 4: Check Results
You should see **10-100 results** (not millions!)

❌ **Too many results?**
- Make the area smaller
- Reduce the time range (try 1 month)

❌ **Zero results?**
- Increase cloud coverage to 50
- Expand time range to full year 2021

### Step 5: Download Images
1. Click on a **thumbnail** to preview
2. Click **"Download"** tab (right panel)
3. Click **"Download Product"** button
4. Save the `.zip` file

**Download 2-3 images to start** (each is ~1GB)

### Step 6: Process Downloaded Files

**Windows (PowerShell/CMD):**
```powershell
# Unzip (you may need 7-Zip or WinRAR installed)
# Right-click .zip files → Extract All

# Then run the processing script
python process_sentinel2_bands.py C:\path\to\extracted\files\
```

**Linux/Mac:**
```bash
# Unzip
cd sentinel2_products
unzip '*.zip'

# Process bands
cd ..
python process_sentinel2_bands.py sentinel2_products/
```

This will create 4-band GeoTIFF files in `imgs/` directory.

### Step 7: Run Detection
```bash
python demo.py
```

Results will be in `result/` directory!

---

## Alternative: Automated Script (Requires API Setup)

If you want automation, use the NEW script I created:

### Setup (one-time):
```bash
pip install requests oauthlib
```

### Configure:
1. Create account at: https://dataspace.copernicus.eu/
2. Edit `download_sentinel2_cdse.py`:
   - Line 16: Add your username
   - Line 17: Add your password
   - Line 21: Set your area coordinates

### Run:
```bash
python download_sentinel2_cdse.py
```

---

## Understanding the Error You Got

```
403 Client Error: Forbidden for url: https://catalogue.dataspace.copernicus.eu/resto/search
```

This happened because:
1. **Old API**: The `sentinelsat` library uses the old SciHub API
2. **SciHub retired**: ESA retired SciHub in late 2023
3. **New system**: Copernicus Data Space uses OAuth2 authentication
4. **Different endpoints**: Complete new API URLs

The script I created (`download_sentinel2_cdse.py`) uses the NEW API that actually works.

---

## File Sizes & Time Estimates

**Per Sentinel-2 Image:**
- Download size: ~1 GB (zipped)
- Extracted size: ~8 GB
- Processing time: 1-2 minutes

**Recommendations:**
- Start with **2-3 images** to test the pipeline
- Each image covers ~100km x 100km
- Download more once you confirm everything works

---

## What You Need for the Model

✅ **Format**: 4-band GeoTIFF
✅ **Bands**: Red (B04), Green (B03), Blue (B02), NIR (B08)
✅ **Band order**: R-G-B-NIR (in that exact order)
✅ **Resolution**: 10 meters per pixel
✅ **Location**: Save in `imgs/` folder
✅ **Year**: 2021 data

The `process_sentinel2_bands.py` script handles all of this automatically!

---

## Troubleshooting

**"I can't find the polygon tool"**
- Look for a square/rectangle icon in the top-left toolbar
- Or just zoom in very close and skip drawing (auto-filters visible area)

**"Download is too slow"**
- ESA servers can be slow during peak hours
- Try downloading at different times
- Consider downloading fewer images

**"Unzip failed - file corrupted"**
- Download was interrupted
- Delete and re-download the .zip file

**"process_sentinel2_bands.py says 'No products found'"**
- Make sure you extracted the .zip files first
- Check that you have .SAFE folders in the directory
- The structure should be: `*.SAFE/GRANULE/*/IMG_DATA/R10m/*.jp2`

---

## Quick Reference: Coordinates

Your ArcGIS portal shows this area:
- **Center**: 0.94°N, 16.71°E
- **Suggested box**:
  - Min: 16.0°E, 0.5°N
  - Max: 17.0°E, 1.5°N

This is in **Central Africa** (likely Gabon/Congo region).

---

**RECOMMENDED APPROACH**: Start with the **manual download** method above. It's the fastest way to get started and requires no API setup!
