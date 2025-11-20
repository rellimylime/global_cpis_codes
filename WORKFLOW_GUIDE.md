# Complete Workflow: Process All 64 Tiles and Create Africa-Wide Shapefile

You have 64 tiles exported from GEE. Here's how to systematically process them all.

## Current Status

- ✅ Downloaded 64 tiles from Google Drive
- ⏳ Need to process all 64 through detection model
- ⏳ Need to merge results into one shapefile

## Why 64 Instead of 50?

The script has `MAX_EXPORTS_PER_RUN = 50`, but you got 64 because:
- Ocean filtering (`SKIP_OCEAN_TILES = True`) kept more land tiles
- Grid boundaries may have created extra tiles at edges
- **This is fine!** More coverage is better.

## Complete Workflow

### Step 1: Find Your Tiles

Your 64 tiles should be in:
- **Google Drive**: `Africa_CPI_Sentinel2/` folder
- **Local Downloads**: `~/Downloads/` or similar

File names should look like: `africa_s2_2021_tile_0042.tif`

### Step 2: Use the Tracking Script

```bash
# Check what needs to be processed
python process_africa_tiles.py --source ~/Downloads/Africa_CPI_Sentinel2 --dry-run

# Process first batch (10 tiles)
python process_africa_tiles.py --source ~/Downloads/Africa_CPI_Sentinel2 --batch-size 10
```

**What this does:**
- Scans for all Africa tiles
- Tracks which have been processed
- Moves next batch (10 tiles) to `imgs/`
- Shows progress

### Step 3: Run Detection

```bash
python batch_detect_africa.py
```

**This will:**
- Process all tiles in `imgs/`
- Create results in `result_africa/[tile_name]/`
- Each tile gets its own folder with shapefiles
- Takes ~2-5 min per tile (GPU) or ~1-2 hours (CPU)

### Step 4: Repeat for All Tiles

After detection completes:

```bash
# Clear imgs/ to make room for next batch (optional)
rm imgs/africa_s2_*.tif

# Process next batch
python process_africa_tiles.py --source ~/Downloads/Africa_CPI_Sentinel2
```

Repeat until all 64 tiles are processed!

**Tip:** You can process in batches of 10-20 tiles to manage disk space.

### Step 5: Merge All Results

Once all tiles are processed:

```bash
python merge_africa_results.py
```

**Output:**
- `africa_cpis_2021.shp` - Single shapefile with ALL CPIs
- `africa_cpis_2021_summary.json` - Statistics summary
- Includes tile_id, confidence, area for each CPI

## Progress Tracking

The script `process_africa_tiles.py` creates `africa_processing_progress.json`:

```json
{
  "processed": ["africa_s2_2021_tile_0001.tif", ...],
  "failed": [],
  "in_progress": [],
  "total_tiles": 64,
  "last_updated": "2024-01-01T12:00:00"
}
```

This tracks your progress automatically!

## File Organization

```
global_cpis_codes/
├── imgs/                                    # Current batch (10-20 tiles)
│   ├── africa_s2_2021_tile_0001.tif
│   ├── africa_s2_2021_tile_0002.tif
│   └── ...
│
├── result_africa/                           # Detection results
│   ├── africa_s2_2021_tile_0001/           # Tile 1 results
│   │   ├── cpis.shp
│   │   ├── cpis.shx
│   │   ├── cpis.dbf
│   │   └── ...
│   ├── africa_s2_2021_tile_0002/           # Tile 2 results
│   └── ...
│
├── africa_cpis_2021.shp                    # FINAL MERGED SHAPEFILE
├── africa_cpis_2021_summary.json           # Statistics
└── africa_processing_progress.json         # Progress tracker
```

## Which Parts of Africa Do You Have?

To see which tiles cover which areas:

### Option 1: Check Tile IDs
```bash
python process_africa_tiles.py --source ~/Downloads/Africa_CPI_Sentinel2 --dry-run
```

This shows tile IDs (e.g., 42, 108, 237, etc.)

### Option 2: View in GIS

After merging results:
1. Open `africa_cpis_2021.shp` in QGIS
2. Color by `tile_id` field
3. See geographic coverage visually

### Option 3: Check Metadata

If your GEE export created `africa_tiles_2021_metadata.json`:
```bash
cat africa_tiles_2021_metadata.json
```

This lists exact bounding boxes for each tile.

## Getting More Tiles (Rest of Africa)

To process the **rest of Africa**:

### 1. Check How Many Tiles You Have
```bash
# Total tiles needed for all of Africa with 2° grid
# ~1000 tiles (ocean-filtered)
```

### 2. Run GEE Export Again

Edit `download_africa_gee.py`:
```python
# Line 52: Increase or process in chunks
MAX_EXPORTS_PER_RUN = 100  # Get next 100 tiles
```

Or modify to skip already-exported tiles:
```python
# Add at line ~240, before creating tiles
already_exported = [1, 5, 9, 12, ...]  # Your existing tile IDs
tiles = [t for t in tiles if t['id'] not in already_exported]
```

### 3. Run Export Script Again
```bash
python download_africa_gee.py
```

This will queue more exports in Google Drive.

## Quick Commands Summary

```bash
# 1. Check progress
python process_africa_tiles.py --source ~/Downloads/Africa_CPI_Sentinel2 --dry-run

# 2. Move next batch to imgs/
python process_africa_tiles.py --source ~/Downloads/Africa_CPI_Sentinel2 --batch-size 10

# 3. Run detection
python batch_detect_africa.py

# 4. Repeat steps 1-3 until all 64 tiles done

# 5. Merge everything
python merge_africa_results.py

# 6. View results
# Open africa_cpis_2021.shp in QGIS or ArcGIS
```

## Expected Timeline

For 64 tiles:

**With GPU:**
- Per tile: 2-5 minutes
- Total: ~4-6 hours
- Process in 4-6 batches

**Without GPU:**
- Per tile: 1-2 hours
- Total: 64-128 hours (3-5 days)
- Process in 6-10 batches

## Disk Space

- **Per tile**: ~300-500 MB (original) + ~50-100 MB (results)
- **64 tiles total**: ~25-40 GB
- **Tip**: Process in batches, delete originals after processing

## Troubleshooting

**"No tiles found"**
```bash
# Check where your tiles are
find ~ -name "africa_s2_*.tif" -type f
# Then use that path
python process_africa_tiles.py --source /path/found
```

**"Out of disk space"**
```bash
# Process fewer tiles per batch
python process_africa_tiles.py --batch-size 5
# Delete source files after processing
```

**"Detection failed for some tiles"**
- Check `fail_img.txt` for failed files
- Failed tiles will be skipped automatically
- Re-run detection script to retry

**"Can't find result shapefiles"**
- Check `result_africa/` directory exists
- Each tile should have a folder with .shp files
- If missing, detection may have failed

## Next Steps After Merging

With `africa_cpis_2021.shp` you can:

1. **Visualize** in QGIS/ArcGIS
2. **Analyze** CPI distribution patterns
3. **Export** to other formats:
   ```bash
   ogr2ogr -f "GeoJSON" africa_cpis_2021.geojson africa_cpis_2021.shp
   ogr2ogr -f "KML" africa_cpis_2021.kml africa_cpis_2021.shp
   ```
4. **Calculate statistics** by country/region
5. **Compare** with previous years' data
6. **Publish** results

## Questions?

- Check progress: `cat africa_processing_progress.json`
- Check summary: `cat africa_cpis_2021_summary.json`
- View logs: `tail -f batch_detect_africa.log` (if created)

Good luck processing all of Africa! 🌍
