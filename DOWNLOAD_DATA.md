# How to Download Sentinel-2 Data for CPI Detection

This guide explains how to get the required GeoTIFF images for running the CPI detection model on 2021 data.

## The Problem

ArcGIS portals often only offer PNG exports, but the model needs **4-band GeoTIFF** (Red-Green-Blue-NIR) from Sentinel-2 satellites.

## Solution: 3 Options

**⚠️ IMPORTANT**: If you get a "403 Forbidden" error, see `QUICK_START_DOWNLOAD.md` for the updated 2024 API method!



### Option 1: Automated Python Script (2024 API)

**Pros**: Automated, downloads exactly what you need
**Cons**: Requires Python setup and API credentials

**Note**: The old `sentinelsat` library no longer works! Use the new script instead.

1. **Install required packages**:
   ```bash
   pip install requests oauthlib
   ```

2. **Create free account** at: https://dataspace.copernicus.eu/

3. **Edit configuration** in `download_sentinel2_cdse.py`:
   - Add your username/password (lines 16-17)
   - Set your area coordinates (line 21)
   - Adjust date range if needed (lines 24-25)

4. **Run the downloader**:
   ```bash
   python download_sentinel2_cdse.py
   ```

5. **Process the downloads** (extract and stack bands):
   ```bash
   # First, unzip the downloaded .zip files
   cd sentinel2_products
   unzip '*.zip'

   # Then stack the bands into 4-band GeoTIFF
   cd ..
   python process_sentinel2_bands.py sentinel2_products/
   ```

6. **Run detection**:
   ```bash
   python demo.py
   ```

---

### Option 2: Google Earth Engine (For Advanced Users)

**Pros**: Powerful filtering, cloud processing
**Cons**: Requires GEE account and authentication

1. **Install Earth Engine**:
   ```bash
   pip install earthengine-api
   ```

2. **Authenticate**:
   ```bash
   earthengine authenticate
   ```

3. **Edit configuration** in `download_sentinel2_gee.py`:
   - Set your area of interest (line 27)
   - Adjust date range (lines 33-34)

4. **Run the script**:
   ```bash
   python download_sentinel2_gee.py
   ```

5. **Choose export method**:
   - Google Drive: Check tasks at https://code.earthengine.google.com/tasks
   - Direct download: Use the URLs printed by the script

---

### Option 3: Manual Download via Copernicus Browser

**Pros**: No coding required, visual interface
**Cons**: Manual clicking, requires band stacking

1. **Go to**: https://browser.dataspace.copernicus.eu/

2. **IMPORTANT: Zoom in closely** to a specific region (NOT all of Africa!)
   - Example: Pick one province or a 50km x 50km area

3. **Set filters** (left sidebar):
   - **Calendar icon**: June 2021 - August 2021 (start with 2-3 months)
   - **Filter icon**:
     - Data source: Sentinel-2
     - Product type: L2A
     - Cloud coverage: 0-20%

4. **Draw area**:
   - Click polygon tool (top left)
   - Draw around your small area of interest
   - Click "Search"

5. **You should see 10-100 results** (not millions!)
   - If you see too many: zoom in more or reduce date range
   - If you see zero: expand date range or cloud coverage

6. **Download**:
   - Click on an image thumbnail
   - Click "Download" tab
   - Download the full product

7. **Process with script**:
   ```bash
   # Unzip downloaded files
   unzip S2*.zip -d sentinel2_downloads/

   # Stack bands
   python process_sentinel2_bands.py sentinel2_downloads/
   ```

---

## Key Tips

### Start Small!
- **Test with 1-3 images first** before downloading hundreds
- Pick a small area (e.g., 0.5° x 0.5° = ~50km x 50km)
- Pick a short time period (1-2 months)

### Area Size Guidelines:
- **Single tile**: ~100km x 100km per Sentinel-2 scene
- **For testing**: Start with 1-2 tiles
- **For production**: Download tiles covering your region of interest

### Date Selection:
- **Dry season** usually has less clouds
- **June-August 2021**: Good for many African regions
- Check cloud cover in preview before downloading

### Coordinate Reference:
Your ArcGIS link shows coordinates: **0.94°N, 16.71°E** (Central Africa)

Example bounding box for that area:
- Min Lon: 16.0, Min Lat: 0.5
- Max Lon: 17.0, Max Lat: 1.5

---

## Troubleshooting

**"Over a million results"**
- ❌ You're looking at too large an area
- ✅ Zoom in to a region about the size of a city/province

**"No images found"**
- Expand date range to full year 2021
- Increase cloud cover to 50%
- Check if coordinates are correct

**"Download failed"**
- Check internet connection
- For large files: Use Google Drive export (Option 2)

**"Bands not found after unzip"**
- Make sure you downloaded L2A products (not L1C)
- Check the .SAFE folder structure exists

---

## What You Need

✅ **Input**: Sentinel-2 Level-2A products (from 2021)
✅ **Format**: 4-band GeoTIFF (R-G-B-NIR, in that order)
✅ **Resolution**: 10 meters per pixel
✅ **Location**: Saved in `imgs/` directory

Then run: `python demo.py`
