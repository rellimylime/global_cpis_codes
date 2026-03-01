# pipeline_master.py
"""
Master pipeline controller for Africa CPI detection.
Handles: GEE export → GDrive download → Detection → Cleanup → Repeat

Can run from scratch or resume at any point.
All state tracked in pipeline_state.json
"""

import ee
import json
import subprocess
import os
import re
from datetime import datetime
import time

# ============ CONFIGURATION ============
GDRIVE_FOLDER = 'Africa_CPI_Sentinel2'
RCLONE_REMOTE = 'gdrive'
BATCH_SIZE_EXPORT = 50  # Export 50 tiles at a time from GEE
BATCH_SIZE_PROCESS = 10  # Process 10 tiles at a time locally
MAX_GDRIVE_TILES = 100  # Keep max 100 tiles in GDrive (~50GB safety margin)
PROJECT_NAME = 'africa-irrigation-mine'

STATE_FILE = 'pipeline_state.json'
# =======================================


def resolve_arid_shapefile():
    """Find the arid-region shapefile directory across branch variants."""
    candidates = [
        'Africa_Arid_Regions_All-shp',
        'SSA_All_Arid_by_Country-shp',
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

def scale_tile_to_u8(in_path: str) -> str:
    """
    Convert 4-band GeoTIFF to Byte and apply fixed scale 0..12520 -> 0..255.
    Returns output path.
    """
    base, ext = os.path.splitext(in_path)
    out_path = base + "_rgbnir_u8.tif"

    # Skip if already scaled
    if os.path.exists(out_path):
        return out_path

    cmd = [
        "gdal_translate",
        "-b", "1", "-b", "2", "-b", "3", "-b", "4",
        "-ot", "Byte",
        "-scale", "0", "12520", "0", "255",
        in_path,
        out_path,
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gdal_translate failed for {in_path}\n{r.stderr}")

    return out_path


def initialize_state():
    """Initialize or load pipeline state."""
    if os.path.exists(STATE_FILE):
        print(f"Loading existing state from {STATE_FILE}...")
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
        
        # Ensure all keys exist (for backward compatibility)
        if 'arid_tiles' not in state:
            state['arid_tiles'] = []
        if 'exported_tiles' not in state:
            state['exported_tiles'] = []
        if 'in_gdrive' not in state:
            state['in_gdrive'] = []
        if 'processed_tiles' not in state:
            state['processed_tiles'] = []
        if 'failed_tiles' not in state:
            state['failed_tiles'] = []
        
        return state
    
    # First time - create state
    print("First run - creating new state file...")
    state = {
        'arid_tiles': [],  # List of all arid tile IDs
        'exported_tiles': [],  # Tiles exported from GEE
        'in_gdrive': [],  # Tiles currently in Google Drive
        'processed_tiles': [],  # Tiles completely processed
        'failed_tiles': [],  # Tiles that failed
        'last_updated': None
    }
    return state

def save_state(state):
    """Save pipeline state."""
    state['last_updated'] = datetime.now().isoformat()
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)
    print(f"✓ State saved to {STATE_FILE}")

def generate_arid_tiles():
    """Generate list of all arid tile IDs (from shapefile intersection)."""
    # Check if cached
    if os.path.exists('arid_tile_ids.json'):
        print("Loading cached arid tile IDs...")
        with open('arid_tile_ids.json', 'r') as f:
            return json.load(f)
    
    print("\n" + "="*80)
    print("Generating arid tile IDs from shapefile...")
    print("This is slow first time but results are cached.")
    print("="*80)
    
    import geopandas as gpd
    from shapely.geometry import box
    
    # Load shapefile
    shapefile_path = resolve_arid_shapefile()
    if shapefile_path is None:
        print("ERROR: Arid shapefile directory not found.")
        print("Expected one of: Africa_Arid_Regions_All-shp, SSA_All_Arid_by_Country-shp")
        return []
    
    print("Loading shapefile...")
    arid_gdf = gpd.read_file(shapefile_path)
    if arid_gdf.crs != 'EPSG:4326':
        print(f"Converting from {arid_gdf.crs} to EPSG:4326...")
        arid_gdf = arid_gdf.to_crs('EPSG:4326')
    
    print("Creating union of arid regions...")
    arid_union = arid_gdf.union_all() if hasattr(arid_gdf, "union_all") else arid_gdf.unary_union
    
    # Generate all tiles
    AFRICA_BBOX = [-17.6, -35.0, 51.4, 37.3]
    GRID_SIZE = 2.0
    
    print("Checking tile intersections...")
    arid_tile_ids = []
    tile_id = 0
    lon = AFRICA_BBOX[0]
    
    while lon < AFRICA_BBOX[2]:
        lat = AFRICA_BBOX[1]
        while lat < AFRICA_BBOX[3]:
            bbox = [lon, lat, 
                   min(lon + GRID_SIZE, AFRICA_BBOX[2]),
                   min(lat + GRID_SIZE, AFRICA_BBOX[3])]
            
            tile_poly = box(*bbox)
            
            if tile_poly.intersects(arid_union):
                arid_tile_ids.append(tile_id)
            
            tile_id += 1
            lat += GRID_SIZE
        lon += GRID_SIZE
    
    # Cache it
    print(f"Caching {len(arid_tile_ids)} arid tiles...")
    with open('arid_tile_ids.json', 'w') as f:
        json.dump(arid_tile_ids, f)
    
    print(f"✓ Found {len(arid_tile_ids)} arid tiles (cached to arid_tile_ids.json)")
    return arid_tile_ids

def check_gdrive_contents():
    """Check what tiles are currently in Google Drive."""
    print("Checking Google Drive contents...")
    result = subprocess.run(
        ['rclone', 'lsf', f'{RCLONE_REMOTE}:{GDRIVE_FOLDER}'],
        capture_output=True, text=True
    )
    
    if result.returncode != 0:
        print(f"Warning: Could not access Google Drive")
        print(f"Make sure rclone is configured with remote name: {RCLONE_REMOTE}")
        return []
    
    tile_ids = set()
    for line in result.stdout.split('\n'):
        match = re.search(r'tile_(\d+)', line)
        if match:
            tile_ids.add(int(match.group(1)))
    
    print(f"  Found {len(tile_ids)} tiles in Google Drive")
    return sorted(tile_ids)

def generate_tile_bbox(tile_id):
    """Generate bbox for a tile ID."""
    AFRICA_BBOX = [-17.6, -35.0, 51.4, 37.3]
    GRID_SIZE = 2.0
    
    lat_steps = int((AFRICA_BBOX[3] - AFRICA_BBOX[1]) / GRID_SIZE) + 1
    
    row = tile_id // lat_steps
    col = tile_id % lat_steps
    
    lon = AFRICA_BBOX[0] + row * GRID_SIZE
    lat = AFRICA_BBOX[1] + col * GRID_SIZE
    
    return [lon, lat, 
            min(lon + GRID_SIZE, AFRICA_BBOX[2]),
            min(lat + GRID_SIZE, AFRICA_BBOX[3])]

def export_tiles_from_gee(tile_ids):
    """Export tiles from GEE to Google Drive."""
    try:
        ee.Initialize(
            #project=PROJECT_NAME 
            )
    except Exception as e:
        print(f"ERROR: Could not initialize Earth Engine")
        print(f"Make sure you've run: earthengine authenticate")
        print(f"Error: {e}")
        return [], [], []
    
    print(f"\nExporting {len(tile_ids)} tiles from GEE...")
    
    successful = []
    skipped = []
    failed = []
    
    for i, tile_id in enumerate(tile_ids, 1):
        print(f"  [{i}/{len(tile_ids)}] Tile {tile_id}...", end=' ', flush=True)
        
        try:
            bbox = generate_tile_bbox(tile_id)
            geometry = ee.Geometry.Rectangle(bbox)
            
            collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                         .filterBounds(geometry)
                         .filterDate('2021-01-01', '2021-12-31')
                         .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
                         .select(['B4', 'B3', 'B2', 'B8']))
            
            count = collection.size().getInfo()
            if count == 0:
                print("⚠ No images")
                skipped.append(tile_id)
                continue
            
            composite = collection.median().clip(geometry)
            
            description = f"africa_s2_2021_tile_{tile_id:04d}"
            
            task = ee.batch.Export.image.toDrive(
                image=composite,
                description=description,
                folder=GDRIVE_FOLDER,
                fileNamePrefix=description,
                region=geometry,
                scale=10,
                crs='EPSG:4326',
                fileFormat='GeoTIFF',
                maxPixels=1e13
            )
            
            task.start()
            print("✓")
            successful.append(tile_id)
            
        except Exception as e:
            print(f"✗ {e}")
            failed.append(tile_id)
    
    print(f"\n  Successful: {len(successful)}")
    print(f"  Skipped (no images): {len(skipped)}")
    print(f"  Failed: {len(failed)}")
    
    return successful, skipped, failed

def process_tiles_with_copy(tile_ids, batch_size):
    """Process tiles using rclone copy instead of mount."""
    print(f"\nProcessing up to {batch_size} tiles...")
    
    # Create imgs/ if needed, but DON'T clear it
    os.makedirs('imgs', exist_ok=True)
    
    # Check what's already downloaded
    existing_files = set(f for f in os.listdir('imgs') if f.endswith('.tif'))
    if existing_files:
        print(f"  Already in imgs/: {len(existing_files)} files")
    
    # Get list of files in GDrive for these tile IDs
    print("Getting list of files from Google Drive...")
    result = subprocess.run(
        ['rclone', 'lsf', f'{RCLONE_REMOTE}:{GDRIVE_FOLDER}'],
        capture_output=True, text=True
    )
    
    files_to_process = []
    for line in result.stdout.split('\n'):
        if not line.strip() or not line.endswith('.tif'):
            continue
        match = re.search(r'tile_(\d+)', line)
        if match and int(match.group(1)) in tile_ids:
            files_to_process.append(line.strip())
    
    files_to_process = sorted(files_to_process)[:batch_size]
    
    if not files_to_process:
        print("No files found to process")
        return []
    
    # Filter out files already downloaded
    files_to_download = [f for f in files_to_process if f not in existing_files]
    
    # Copy only new files from GDrive to imgs/
    if files_to_download:
        print(f"Copying {len(files_to_download)} new tiles from Google Drive to imgs/...")
        for i, filename in enumerate(files_to_download, 1):
            print(f"  [{i}/{len(files_to_download)}] {filename}...", end=' ', flush=True)
            result = subprocess.run([
                'rclone', 'copy',
                f'{RCLONE_REMOTE}:{GDRIVE_FOLDER}/{filename}',
                'imgs/'
            ], capture_output=True)
            
            if result.returncode == 0:
                print("✓")
            else:
                print(f"✗")
    else:
        print(f"All {len(files_to_process)} tiles already in imgs/ - skipping download")
    
    # Scale/standardize tiles in imgs/
    print("\nScaling tiles to uint8 (0..12520 -> 0..255)...")
    scaled_paths = []
    for f in sorted(os.listdir("imgs")):
        if not f.endswith(".tif"):
            continue
        p = os.path.join("imgs", f)

        # avoid re-scaling already-scaled outputs
        if p.endswith("_rgbnir_u8.tif"):
            scaled_paths.append(p)
            continue

        try:
            scaled_paths.append(scale_tile_to_u8(p))
        except Exception as e:
            print(f"✗ Scaling failed for {f}: {e}")
            continue

    print(f"✓ Scaled {len(scaled_paths)} tiles")

    # Run detection
    print("\nRunning CPI detection...")
    result = subprocess.run(
        ['python', 'batch_detect_africa.py', '--auto'],
        capture_output=True,
        text=True
    )
    
    # Print output
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print("ERRORS:", result.stderr)

    if result.returncode != 0:
        print("✗ Detection failed")
        return []
    
    # Get processed tile IDs
    processed = []
    for filename in files_to_process:
        match = re.search(r'tile_(\d+)', filename)
        if match:
            processed.append(int(match.group(1)))
    
    # Clean up imgs/
    print("\nCleaning up imgs/...")
    deleted_count = 0
    for f in os.listdir('imgs'):
        if f.endswith('.tif'):
            os.remove(os.path.join('imgs', f))
            deleted_count += 1
    print(f"✓ Deleted {deleted_count} tiles from imgs/")
    
    return processed

def delete_from_gdrive(tile_ids):
    """Delete processed tiles from Google Drive (including trash)."""
    print(f"\nDeleting {len(tile_ids)} tiles from Google Drive...")
    
    # Get all files in folder
    result = subprocess.run(
        ['rclone', 'lsf', f'{RCLONE_REMOTE}:{GDRIVE_FOLDER}'],
        capture_output=True, text=True
    )
    
    # Find files matching tile IDs
    files_to_delete = []
    for line in result.stdout.split('\n'):
        for tile_id in tile_ids:
            if f'tile_{tile_id:04d}' in line and line.strip():
                files_to_delete.append(line.strip())
    
    if not files_to_delete:
        print("No files found to delete")
        return
    
    # Delete files
    for i, filename in enumerate(files_to_delete, 1):
        print(f"  [{i}/{len(files_to_delete)}] {filename}...", end=' ', flush=True)
        subprocess.run([
            'rclone', 'delete', 
            f'{RCLONE_REMOTE}:{GDRIVE_FOLDER}/{filename}'
        ], capture_output=True)
        print("✓")
    
    # Empty trash
    print("Emptying Google Drive trash...")
    subprocess.run([
        'rclone', 'cleanup', f'{RCLONE_REMOTE}:'
    ], capture_output=True)
    
    print(f"✓ Deleted {len(files_to_delete)} files and emptied trash")

def print_status(state):
    """Print pipeline status."""
    total_arid = len(state['arid_tiles'])
    processed = len(state['processed_tiles'])
    in_gdrive = len(state['in_gdrive'])
    failed = len(state['failed_tiles'])
    remaining = total_arid - processed - failed
    
    print("\n" + "="*80)
    print("PIPELINE STATUS")
    print("="*80)
    print(f"Total arid tiles: {total_arid}")
    print(f"Processed: {processed} ({100*processed/total_arid:.1f}%)" if total_arid > 0 else "Processed: 0")
    print(f"In Google Drive: {in_gdrive}")
    print(f"Failed (no images): {failed}")
    print(f"Remaining: {remaining}")
    print("="*80)

def main():
    print("="*80)
    print("Africa CPI Detection - Master Pipeline")
    print("="*80)
    
    # Load or initialize state
    state = initialize_state()
    
    # Step 1: Generate arid tiles list if needed
    if not state['arid_tiles']:
        print("\nStep 1: Generating arid tiles list...")
        state['arid_tiles'] = generate_arid_tiles()
        if not state['arid_tiles']:
            print("ERROR: Could not generate arid tiles. Exiting.")
            return
        save_state(state)
    else:
        print(f"\nStep 1: Using existing arid tiles list ({len(state['arid_tiles'])} tiles)")
    
    # Step 2: Sync state with Google Drive
    print("\nStep 2: Syncing with Google Drive...")
    state['in_gdrive'] = check_gdrive_contents()
    save_state(state)
    
    # Print status
    print_status(state)
    
    # Step 3: Determine what to do
    arid_set = set(state['arid_tiles'])
    processed_set = set(state['processed_tiles'])
    in_gdrive_set = set(state['in_gdrive'])
    failed_set = set(state['failed_tiles'])
    
    # Tiles that need exporting
    need_export = arid_set - processed_set - in_gdrive_set - failed_set
    
    # Tiles ready to process (in gdrive but not processed)
    ready_to_process = in_gdrive_set - processed_set
    
    print(f"\nReady to process: {len(ready_to_process)} tiles")
    print(f"Need to export: {len(need_export)} tiles")
    
    # Step 4: Process tiles if any are ready
    # Step 4: Process tiles if any are ready
    if ready_to_process:
        print("\n" + "="*80)
        print("PROCESSING PHASE")
        print("="*80)
        
        batch = sorted(ready_to_process)[:BATCH_SIZE_PROCESS]
        print(f"\nProcessing batch of {len(batch)} tiles")
        print(f"Tile IDs: {batch[:10]}" + (f"... and {len(batch)-10} more" if len(batch) > 10 else ""))
        
        # Use rclone copy instead of mount (HPC compatible)
        processed = process_tiles_with_copy(batch, BATCH_SIZE_PROCESS)
            
        if processed:
            # Update state
            state['processed_tiles'].extend(processed)
            state['processed_tiles'] = list(set(state['processed_tiles']))  # Remove duplicates
            
            # Delete from GDrive
            delete_from_gdrive(processed)
            
            # Update in_gdrive
            state['in_gdrive'] = check_gdrive_contents()
            
            save_state(state)
            print(f"\n✓ Processed {len(processed)} tiles")
        else:
            print("\n✗ No tiles were processed")
    
    # Step 5: Export more tiles if there's room
    if need_export and len(state['in_gdrive']) < MAX_GDRIVE_TILES:
        print("\n" + "="*80)
        print("EXPORT PHASE")
        print("="*80)
        
        # How many can we export?
        room_in_gdrive = MAX_GDRIVE_TILES - len(state['in_gdrive'])
        to_export = min(BATCH_SIZE_EXPORT, room_in_gdrive, len(need_export))
        
        print(f"\nGoogle Drive space: {len(state['in_gdrive'])}/{MAX_GDRIVE_TILES} tiles")
        print(f"Room for: {room_in_gdrive} more tiles")
        print(f"Exporting: {to_export} tiles")
        
        export_batch = sorted(need_export)[:to_export]
        
        successful, skipped, failed = export_tiles_from_gee(export_batch)
        
        # Update state
        state['exported_tiles'].extend(successful)
        state['exported_tiles'] = list(set(state['exported_tiles']))  # Remove duplicates
        
        state['failed_tiles'].extend(skipped + failed)
        state['failed_tiles'] = list(set(state['failed_tiles']))  # Remove duplicates
        
        save_state(state)
        
        print(f"\n✓ Started export for {len(successful)} tiles")
        if skipped:
            print(f"⚠ Skipped {len(skipped)} tiles (no images available)")
        if failed:
            print(f"✗ Failed {len(failed)} tiles")
        print("\nWait for GEE tasks to complete at: https://code.earthengine.google.com/tasks")
        print("Then run this script again to process them")
    
    # Final status
    print_status(state)
    
    # What to do next
    print("\n" + "="*80)
    print("NEXT STEPS")
    print("="*80)
    
    if need_export and len(state['in_gdrive']) >= MAX_GDRIVE_TILES:
        print("\n⚠ Google Drive at capacity - process tiles first")
        print("Run: python pipeline_master.py")
    elif ready_to_process:
        print("\nMore tiles ready to process")
        print("Run: python pipeline_master.py")
    elif need_export and len(state['in_gdrive']) < MAX_GDRIVE_TILES:
        print("\nWaiting for GEE export tasks to complete")
        print("Check: https://code.earthengine.google.com/tasks")
        print("Then run: python pipeline_master.py")
    else:
        print("\n✓ ALL TILES COMPLETED!")
        print("\nCreate final shapefile:")
        print("  python merge_africa_results.py")

if __name__ == '__main__':
    main()
