"""
Google Earth Engine script to download Sentinel-2 for all of Africa in chunks.

This script:
1. Divides Africa into manageable tiles
2. Creates cloud-free 2021 composites for each tile
3. Exports to Google Drive with R-G-B-NIR bands
4. Ready for CPI detection model

Setup:
1. Install: pip install earthengine-api
2. Authenticate: earthengine authenticate
3. Configure settings below
4. Run: python download_africa_gee.py

After exports complete, download from Google Drive and run:
5. python process_sentinel2_bands.py (if needed)
6. python batch_detect_africa.py
"""

import ee
import json
import os
from datetime import datetime

# Initialize Earth Engine
try:
    ee.Initialize()
    print("✓ Earth Engine initialized")
except:
    print("ERROR: Earth Engine not authenticated.")
    print("Run: earthengine authenticate")
    exit(1)

# ============ CONFIGURATION ============

# Africa bounding box [min_lon, min_lat, max_lon, max_lat]
AFRICA_BBOX = [-17.6, -35.0, 51.4, 37.3]

# Grid size in degrees (2.0 = ~222km tiles)
# Smaller = more tiles but more manageable file sizes
GRID_SIZE = 2.0

# Year to process
YEAR = 2021

# Cloud coverage threshold for image selection
MAX_CLOUD_COVER = 30

# Export settings
EXPORT_FOLDER = 'Africa_CPI_Sentinel2'  # Folder in Google Drive
EXPORT_SCALE = 10  # meters per pixel (Sentinel-2 native resolution)
MAX_EXPORTS_PER_RUN = 50  # Limit to avoid overwhelming GEE

# Skip tiles that are mostly ocean (saves time/storage)
SKIP_OCEAN_TILES = True

# =======================================


def create_grid(bbox, grid_size):
    """Create grid of tiles covering Africa."""
    min_lon, min_lat, max_lon, max_lat = bbox

    tiles = []
    lon = min_lon
    tile_id = 0

    while lon < max_lon:
        lat = min_lat
        while lat < max_lat:
            tile_bbox = [lon, lat, min(lon + grid_size, max_lon), min(lat + grid_size, max_lat)]
            tiles.append({
                'id': tile_id,
                'bbox': tile_bbox,
                'center_lon': (tile_bbox[0] + tile_bbox[2]) / 2,
                'center_lat': (tile_bbox[1] + tile_bbox[3]) / 2
            })
            tile_id += 1
            lat += grid_size
        lon += grid_size

    return tiles


def get_sentinel2_composite(bbox, year, max_cloud):
    """Create cloud-free composite for a tile."""

    # Create geometry for tile
    geometry = ee.Geometry.Rectangle(bbox)

    # Date range for the year
    start_date = f'{year}-01-01'
    end_date = f'{year}-12-31'

    # Get Sentinel-2 collection
    collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                  .filterBounds(geometry)
                  .filterDate(start_date, end_date)
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_cloud))
                  .select(['B4', 'B3', 'B2', 'B8']))  # Red, Green, Blue, NIR

    # Create median composite (cloud-free)
    composite = collection.median()

    # Clip to tile boundary
    composite = composite.clip(geometry)

    return composite, collection.size()


def is_mostly_ocean(lon, lat):
    """Simple heuristic to skip ocean tiles."""
    # This is a rough approximation
    # Skip tiles in Atlantic/Indian Ocean far from coast

    # Atlantic Ocean west of Africa
    if lon < -10 and lat < 15:
        return True

    # Indian Ocean east of Africa
    if lon > 45 and lat < -10:
        return True

    # Mediterranean (not really ocean for our purposes)
    if lat > 30 and lon < 10:
        return False

    return False


def export_tile(tile, composite, folder):
    """Export tile to Google Drive."""

    tile_id = tile['id']
    bbox = tile['bbox']

    # Create description for the task
    description = f"africa_s2_{YEAR}_tile_{tile_id:04d}"

    # Create geometry
    geometry = ee.Geometry.Rectangle(bbox)

    # Export task
    task = ee.batch.Export.image.toDrive(
        image=composite,
        description=description,
        folder=folder,
        fileNamePrefix=description,
        region=geometry,
        scale=EXPORT_SCALE,
        crs='EPSG:4326',
        fileFormat='GeoTIFF',
        maxPixels=1e13,
        formatOptions={
            'cloudOptimized': True
        }
    )

    task.start()

    return task, description


def load_export_progress():
    """Load record of which tiles have been exported."""
    progress_file = 'gee_export_progress.json'

    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            return json.load(f)

    return {
        'exported_tile_ids': [],
        'failed_tile_ids': [],
        'total_exported': 0,
        'export_history': []
    }


def save_export_progress(progress):
    """Save record of exported tiles."""
    with open('gee_export_progress.json', 'w') as f:
        json.dump(progress, f, indent=2)


def main():
    print("=" * 80)
    print("Africa-Scale Sentinel-2 Download via Google Earth Engine")
    print("=" * 80)

    # Load previous export progress
    export_progress = load_export_progress()
    already_exported = set(export_progress['exported_tile_ids'])

    if already_exported:
        print(f"\n✓ Found {len(already_exported)} previously exported tiles")

    # Create grid
    print(f"\n1. Creating grid...")
    print(f"   Region: {AFRICA_BBOX}")
    print(f"   Grid size: {GRID_SIZE}° (~{int(GRID_SIZE * 111)}km)")

    all_tiles = create_grid(AFRICA_BBOX, GRID_SIZE)
    print(f"   Total tiles: {len(all_tiles)}")

    # Filter ocean tiles if requested
    if SKIP_OCEAN_TILES:
        tiles_before = len(all_tiles)
        all_tiles = [t for t in all_tiles if not is_mostly_ocean(t['center_lon'], t['center_lat'])]
        print(f"   Filtered ocean tiles: {tiles_before} → {len(all_tiles)} tiles")

    # Skip already exported tiles
    tiles = [t for t in all_tiles if t['id'] not in already_exported]

    print(f"\n   Already exported: {len(already_exported)}")
    print(f"   Remaining: {len(tiles)}")
    print(f"   Progress: {len(already_exported)}/{len(all_tiles)} ({100*len(already_exported)/len(all_tiles):.1f}%)")

    if len(tiles) == 0:
        print("\n✓ All tiles have been exported!")
        print(f"   Total: {len(all_tiles)} tiles")
        return

    # Estimate
    est_size_gb = len(tiles) * 0.5  # ~500MB per tile
    print(f"\n   Estimated size for remaining: ~{est_size_gb:.0f} GB")
    print(f"   Google Drive folder: {EXPORT_FOLDER}/")

    # Limit exports per run
    batch_size = min(len(tiles), MAX_EXPORTS_PER_RUN)
    tiles = tiles[:batch_size]

    print(f"\n   Exporting next batch: {batch_size} tiles")
    print(f"   Tile IDs: {tiles[0]['id']} to {tiles[-1]['id']}")

    response = input(f"\n   Start exports for {len(tiles)} tiles? (yes/no): ")
    if response.lower() != 'yes':
        print("   Cancelled.")
        return

    # Process each tile
    print(f"\n2. Creating composites and starting exports...")
    print("=" * 80)

    tasks = []
    successful_tiles = []
    failed_tiles = []

    for i, tile in enumerate(tiles):
        tile_id = tile['id']
        bbox = tile['bbox']

        print(f"\nTile {i+1}/{len(tiles)} (ID: {tile_id})")
        print(f"  Bounds: {bbox}")

        try:
            # Create composite
            composite, image_count = get_sentinel2_composite(bbox, YEAR, MAX_CLOUD_COVER)

            # Check if any images available
            count = image_count.getInfo()
            print(f"  Images found: {count}")

            if count == 0:
                print(f"  ⚠ No images (skipping)")
                failed_tiles.append(tile)
                continue

            # Export
            task, description = export_tile(tile, composite, EXPORT_FOLDER)
            tasks.append((tile_id, description, task))
            successful_tiles.append(tile)

            print(f"  ✓ Export started: {description}")

        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed_tiles.append(tile)

    print("\n" + "=" * 80)
    print("Export Tasks Started!")
    print("=" * 80)
    print(f"\nSuccessful: {len(successful_tiles)}/{len(tiles)} tiles")
    print(f"Failed/Skipped: {len(failed_tiles)}/{len(tiles)} tiles")

    print(f"\nAll exports are queued to Google Drive folder: {EXPORT_FOLDER}/")
    print("\nMonitor progress at: https://code.earthengine.google.com/tasks")

    print("\nExport tasks will run in the background (may take hours/days).")
    print("You can close this script - tasks will continue on GEE servers.")

    # Update export progress
    successful_tile_ids = [t['id'] for t in successful_tiles]
    failed_tile_ids = [t['id'] for t in failed_tiles]

    export_progress['exported_tile_ids'].extend(successful_tile_ids)
    export_progress['failed_tile_ids'].extend(failed_tile_ids)
    export_progress['total_exported'] = len(export_progress['exported_tile_ids'])

    export_progress['export_history'].append({
        'timestamp': datetime.now().isoformat(),
        'batch_size': len(tiles),
        'successful': len(successful_tiles),
        'failed': len(failed_tiles),
        'tile_ids': successful_tile_ids
    })

    save_export_progress(export_progress)
    print(f"\n✓ Export progress saved to: gee_export_progress.json")

    # Save batch metadata
    metadata = {
        'year': YEAR,
        'grid_size': GRID_SIZE,
        'batch_size': len(tiles),
        'successful': len(successful_tiles),
        'failed': len(failed_tiles),
        'timestamp': datetime.now().isoformat(),
        'tiles': successful_tiles,
        'tasks': [(tid, desc) for tid, desc, _ in tasks]
    }

    metadata_file = f'africa_tiles_{YEAR}_batch_{len(export_progress["export_history"])}.json'
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"✓ Batch metadata saved to: {metadata_file}")

    # Calculate remaining tiles
    total_tiles_in_africa = len(all_tiles)
    remaining_tiles = total_tiles_in_africa - len(export_progress['exported_tile_ids'])

    print("\n" + "=" * 80)
    print("EXPORT PROGRESS")
    print("=" * 80)
    print(f"\nTotal tiles for Africa: {total_tiles_in_africa}")
    print(f"Exported so far: {len(export_progress['exported_tile_ids'])}")
    print(f"Remaining: {remaining_tiles}")
    print(f"Progress: {100*len(export_progress['exported_tile_ids'])/total_tiles_in_africa:.1f}%")

    print("\n" + "=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print("\n1. Wait for exports to complete (check GEE tasks page)")
    print(f"2. Download tiles from Google Drive → {EXPORT_FOLDER}/")
    print("3. Process tiles:")
    print("   python process_africa_tiles.py --source ~/Downloads/Africa_CPI_Sentinel2")
    print("   python batch_detect_africa.py")

    if remaining_tiles > 0:
        print(f"\n4. Export next batch ({remaining_tiles} tiles remaining):")
        print("   python download_africa_gee.py")
        print(f"\n   This will automatically export the next {min(remaining_tiles, MAX_EXPORTS_PER_RUN)} tiles")
    else:
        print("\n✓ ALL TILES EXPORTED! No more batches needed.")

    print("\nTip: You can download and process tiles incrementally!")
    print("     No need to wait for all exports to finish.\n")


if __name__ == '__main__':
    main()
