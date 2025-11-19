# Detecting CPIs Across All of Africa

You want to detect CPIs across the entire African continent for 2021. Here are the realistic approaches:

## The Challenge

- **Africa size**: ~30 million km²
- **Sentinel-2 tiles needed**: ~2,000+ tiles
- **Data volume**: ~2-5 TB of raw imagery
- **Processing time**: Days to weeks
- **Storage**: Several TB required

## ⭐ BEST APPROACH: Use Digital Earth Africa (Pre-processed!)

**What you were looking at in ArcGIS is actually perfect!**

The dataset at your ArcGIS portal (https://uneca.africageoportal.com/) is **Digital Earth Africa's GeoMAD** - an annual cloud-free composite already processed for you!

### Digital Earth Africa GeoMAD:
- ✅ **Annual cloud-free composite** for all of Africa
- ✅ **Already processed** - no need to download thousands of scenes
- ✅ **2021 data available**
- ✅ **Has R-G-B-NIR bands** (exactly what you need!)
- ✅ **Continent-scale** ready to use

### How to Access Digital Earth Africa Data:

#### Option 1: Digital Earth Africa Maps (Easiest!)

**URL**: https://maps.digitalearth.africa/

1. **Select layer**: "Sentinel-2 Annual GeoMAD"
2. **Select year**: 2021
3. **Download tiles**:
   - Click "Tools" → "Download Data"
   - Select region
   - Export as GeoTIFF with all bands

#### Option 2: Digital Earth Africa Sandbox (Python - Most Powerful!)

This is a **free Jupyter environment** with all of Africa's Sentinel-2 data already loaded!

**URL**: https://sandbox.digitalearth.africa/

```python
# Example code to download 2021 GeoMAD for a region
import datacube
from deafrica_tools.spatial import xr_to_geotiff

dc = datacube.Datacube(app='cpi_detection')

# Define your area (or loop through all of Africa)
query = {
    'product': 'gm_s2_annual',  # GeoMAD annual composite
    'time': '2021',
    'x': (16.0, 17.0),  # Longitude
    'y': (0.5, 1.5),    # Latitude
    'output_crs': 'EPSG:4326',
    'resolution': (-0.0001, 0.0001)  # ~10m
}

# Load data
ds = dc.load(**query)

# Select R-G-B-NIR bands
bands = ds[['red', 'green', 'blue', 'nir']]

# Export to GeoTIFF
xr_to_geotiff(bands, 'output.tif')
```

**Advantages:**
- No download limits
- Pre-processed and cloud-free
- Analysis-ready data
- Free to use

#### Option 3: Direct AWS Access

Digital Earth Africa data is on AWS S3 (free access, no egress fees for Africa):

```python
import rioxarray

url = "s3://deafrica-sentinel-2-gm/gm_s2_annual/2021/..."
data = rioxarray.open_rasterio(url)
```

## Approach 2: Google Earth Engine (Automated Continental Analysis)

Create cloud-free composites and export for Africa:

```python
# Create annual cloud-free composite for Africa
import ee
ee.Initialize()

# Define Africa boundary
africa = ee.FeatureCollection("USDOS/LSIB_SIMPLE/2017") \
    .filter(ee.Filter.eq('continent', 'Africa'))

# Get 2021 Sentinel-2 composite
s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
    .filterBounds(africa) \
    .filterDate('2021-01-01', '2021-12-31') \
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
    .select(['B4', 'B3', 'B2', 'B8']) \
    .median()  # Cloud-free composite

# Export to Google Drive in tiles
# (Africa is too big for single export)
```

**Note**: You'll need to tile Africa into smaller regions for export.

## Approach 3: Download Raw Sentinel-2 (My Script)

Use the `download_africa_grid.py` script I created:

```bash
# Edit configuration (username, password, region)
python download_africa_grid.py
```

**Warning**: This downloads **~2000+ images** (~2-5 TB)

### Realistic Timeline:
- Download: 1-3 days
- Processing: 2-5 days
- Detection: 3-7 days
- **Total: 1-2 weeks minimum**

## 📊 Recommended Workflow for All of Africa

### Phase 1: Test (1 day)
1. Pick ONE country or region (~100km x 100km)
2. Download 2-3 test images (from Digital Earth Africa)
3. Run CPI detection
4. Verify results look good

### Phase 2: Regional Scale (1 week)
1. Define priority regions (e.g., Sahel, East Africa)
2. Use Digital Earth Africa for those regions
3. Process in batches

### Phase 3: Continental Scale (2-4 weeks)
1. Use Digital Earth Africa GeoMAD 2021
2. Split continent into manageable tiles (~200km x 200km)
3. Run batch detection: `python batch_detect_africa.py`
4. Merge results

## Cloud Cover Filter in Copernicus Browser

To find the cloud cover option:

1. Go to: https://browser.dataspace.copernicus.eu/
2. Click **"Show advanced search"** or **"Advanced"** button
3. Look for **"Cloud coverage (%)"** slider (0-100%)
4. Or after searching, switch to **"Table"** view to see cloud % column

**But** - for all of Africa, use the automated approaches above instead of manual browser download!

## File Organization for Continental Analysis

```
africa_cpi_project/
├── sentinel2_products/          # Downloaded raw data (~TB)
├── imgs/                         # Processed 4-band GeoTIFFs
│   ├── tile_001.tif
│   ├── tile_002.tif
│   └── ...
├── result_africa/                # Detection results
│   ├── tile_001/
│   ├── tile_002/
│   └── ...
├── tiles_processed.json         # Grid metadata
└── africa_cpi_summary.shp       # Final merged results
```

## Computational Requirements

For all of Africa:

**Storage:**
- Raw downloads: 2-5 TB
- Processed images: 500 GB - 1 TB
- Results: 50-100 GB
- **Total: 3-6 TB**

**RAM:**
- Model inference: 8-16 GB
- Image processing: 16-32 GB recommended

**GPU:**
- Highly recommended (100x faster!)
- Detection on CPU: ~5 min per image
- Detection on GPU: ~2-3 seconds per image

**Time Estimates (2000 images):**
- With GPU: 3-5 days total
- Without GPU: 1-2 months total

## 🎯 My Recommendation

### START HERE:

**Step 1**: Use Digital Earth Africa Maps
- Go to: https://maps.digitalearth.africa/
- Select "Sentinel-2 Annual GeoMAD" → Year 2021
- Download one test region (GeoTIFF with all bands)
- This gives you analysis-ready, cloud-free data!

**Step 2**: Test the pipeline
```bash
# Save downloaded file to imgs/
mv Downloads/geomad_2021_test.tif imgs/
python demo.py
```

**Step 3**: If results are good
- Use Digital Earth Africa Sandbox (Python) for automation
- Download data for all regions systematically
- Process in batches with `batch_detect_africa.py`

### Don't Start With:
- ❌ Downloading 2000+ individual Sentinel-2 scenes manually
- ❌ Processing all of Africa at once
- ❌ Using the Copernicus Browser for continent-scale work

### Do This Instead:
- ✅ Use pre-processed annual composites (Digital Earth Africa GeoMAD)
- ✅ Start with one region to test (100km x 100km)
- ✅ Automate with Python scripts
- ✅ Process in parallel batches

## Scripts I Created for You

1. **download_africa_grid.py** - Grid-based download for all of Africa
2. **batch_detect_africa.py** - Batch CPI detection on many images
3. **download_sentinel2_cdse.py** - Download from Copernicus (2024 API)
4. **process_sentinel2_bands.py** - Stack R-G-B-NIR bands

## Quick Links

- **Digital Earth Africa Maps**: https://maps.digitalearth.africa/
- **DE Africa Sandbox** (Free Jupyter): https://sandbox.digitalearth.africa/
- **DE Africa Docs**: https://docs.digitalearthafrica.org/
- **DE Africa Data Catalog**: https://www.digitalearthafrica.org/platform-resources/services/open-data-cube
- **Copernicus Browser**: https://browser.dataspace.copernicus.eu/

## The Bottom Line

**The GeoMAD data you found on the ArcGIS portal is EXACTLY what you need!**

It's an annual cloud-free composite of all of Africa, with the R-G-B-NIR bands required by the CPI detection model. You just need to access it from the right place (Digital Earth Africa) instead of trying to download it as PNG from ArcGIS.

Digital Earth Africa already did the hard work of:
- Finding all Sentinel-2 images for Africa
- Filtering clouds
- Creating annual composites
- Making it analysis-ready

Use their tools - don't reinvent the wheel!
