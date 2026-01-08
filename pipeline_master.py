# pipeline_master.py
"""
Master pipeline controller for Africa CPI detection.
Handles: GEE export -> GDrive download -> Detection -> Cleanup -> Repeat

Refactored to handle:
- 1 Tile ID = Multiple GeoTIFF files (Earth Engine split behavior)
- Corrupt file retries
- Isolated batch directories
"""

import ee
import json
import subprocess
import os
import re
import shutil
import time
from datetime import datetime

# ============ CONFIGURATION ============
GDRIVE_FOLDER = 'Africa_CPI_Sentinel2'
RCLONE_REMOTE = 'gdrive'

# Directory Isolation (Fix #2)
RAW_DIR = 'imgs_batch'       # Where raw split tiles go
SCALED_DIR = 'imgs_batch_u8' # Where combined/scaled u8 tiles go

BATCH_SIZE_EXPORT = 50   # Export 50 tiles at a time from GEE
BATCH_SIZE_PROCESS = 10  # Process 10 tiles at a time locally
MAX_GDRIVE_TILES = 100   # Keep max 100 tiles in GDrive (~50GB safety margin)

STATE_FILE = 'pipeline_state.json'
# =======================================

TILE_RE = re.compile(r"tile_(\d+)")

def tile_id_from_name(name: str) -> int | None:
    m = TILE_RE.search(name)
    return int(m.group(1)) if m else None

def setup_batch_dirs():
    """Clear and recreate batch directories to prevent ghost files (Fix #2)."""
    if os.path.exists(RAW_DIR):
        shutil.rmtree(RAW_DIR)
    if os.path.exists(SCALED_DIR):
        shutil.rmtree(SCALED_DIR)
    os.makedirs(RAW_DIR)
    os.makedirs(SCALED_DIR)

def download_file(filename):
    """Helper to download a single file using rclone."""
    subprocess.run([
        'rclone', 'copy',
        f'{RCLONE_REMOTE}:{GDRIVE_FOLDER}/{filename}',
        RAW_DIR
    ], check=True, capture_output=True)

def scale_tile_to_u8(filename: str) -> str:
    """
    Convert 4-band GeoTIFF to Byte 0..255.
    Reads from RAW_DIR, writes to SCALED_DIR.
    Returns the output filename.
    """
    in_path = os.path.join(RAW_DIR, filename)
    base, ext = os.path.splitext(filename)
    out_name = base + "_rgbnir_u8.tif"
    out_path = os.path.join(SCALED_DIR, out_name)

    # Skip if somehow already exists (though we clean dirs now)
    if os.path.exists(out_path):
        return out_name

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
        raise RuntimeError(f"gdal_translate failed: {r.stderr}")

    return out_name

def initialize_state():
    """Initialize or load pipeline state."""
    if os.path.exists(STATE_FILE):
        print(f"Loading existing state from {STATE_FILE}...")
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
        # Ensure keys exist
        for key in ['arid_tiles', 'exported_tiles', 'in_gdrive', 'processed_tiles', 'failed_tiles']:
            if key not in state: state[key] = []
        return state
    
    print("First run - creating new state file...")
    return {
        'arid_tiles': [], 'exported_tiles': [], 'in_gdrive': [],
        'processed_tiles': [], 'failed_tiles': [], 'last_updated': None
    }

def save_state(state):
    state['last_updated'] = datetime.now().isoformat()
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def check_gdrive_contents():
    """Check what tiles are currently in Google Drive."""
    print("Checking Google Drive contents...")
    result = subprocess.run(
        ['rclone', 'lsf', f'{RCLONE_REMOTE}:{GDRIVE_FOLDER}'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Warning: Could not access Google Drive (rclone error)")
        return []
    
    tile_ids = set()
    for line in result.stdout.splitlines():
        match = TILE_RE.search(line)
        if match:
            tile_ids.add(int(match.group(1)))
    
    print(f"  Found {len(tile_ids)} tiles in Google Drive")
    return sorted(tile_ids)

def process_tiles_with_copy(tile_ids_to_process):
    """
    Main processing logic.
    - Groups files by Tile ID (Fix #1)
    - Downloads and scales (Fix #3: with retry)
    - Runs detection on isolated folder (Fix #2)
    """
    print(f"\nProcessing batch of {len(tile_ids_to_process)} tiles...")
    
    # 1. Clean workspace
    setup_batch_dirs()

    # 2. Map Tile IDs to Files in Drive
    print("Listing files in Drive to build file groups...")
    result = subprocess.run(
        ['rclone', 'lsf', f'{RCLONE_REMOTE}:{GDRIVE_FOLDER}'],
        capture_output=True, text=True
    )
    
    files_by_tile = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.endswith(".tif"): continue
        tid = tile_id_from_name(line)
        if tid is not None and tid in tile_ids_to_process:
            files_by_tile.setdefault(tid, []).append(line)

    if not files_by_tile:
        print("No matching files found in Drive for this batch.")
        return []

    # 3. Download and Scale Loop
    processed_tile_ids = []
    failed_tile_ids = []
    batch_list_files = [] # Only scaled files go here (Fix #6)

    print(f"Found files for {len(files_by_tile)} tiles. Starting download/scale...")

    for tid, files in files_by_tile.items():
        tile_failed = False
        scaled_files_for_tile = []

        for filename in files:
            try:
                # Attempt 1
                try:
                    download_file(filename)
                    out_name = scale_tile_to_u8(filename)
                    scaled_files_for_tile.append(out_name)
                except Exception as e:
                    # Fix #3: Corrupt file handling - Delete, Re-download, Retry
                    print(f"⚠ Error on {filename}: {e}. Retrying once...")
                    
                    local_raw = os.path.join(RAW_DIR, filename)
                    if os.path.exists(local_raw): os.remove(local_raw)
                    
                    download_file(filename) # Re-download
                    out_name = scale_tile_to_u8(filename) # Re-scale
                    scaled_files_for_tile.append(out_name)

            except Exception as final_e:
                print(f"✗ Failed {filename} after retry: {final_e}")
                tile_failed = True
                break # Stop processing this tile completely
        
        if tile_failed:
            failed_tile_ids.append(tid)
        else:
            batch_list_files.extend(scaled_files_for_tile)
            processed_tile_ids.append(tid)

    if not batch_list_files:
        print("No files were successfully scaled.")
        return []

    # 4. Write _batch_list.txt (Fix #6)
    list_path = os.path.join(SCALED_DIR, "_batch_list.txt")
    with open(list_path, "w") as fp:
        for name in batch_list_files:
            fp.write(name + "\n")

    # 5. Run Detection (Fix #5: Separate Process)
    print(f"\nRunning Detection on {len(batch_list_files)} files...")
    # Passing the SCALED_DIR as the image directory
    cmd = ['python', 'batch_detect_africa.py', '--auto', '--img_dir', SCALED_DIR]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print("--- Detection Output ---")
    print(result.stdout)
    if result.stderr: print(f"Errors: {result.stderr}")
    print("------------------------")

    # Fix #4: If detection fails, STOP pipeline
    if result.returncode != 0:
        raise RuntimeError("Detection script crashed! Stopping pipeline to prevent Drive overflow.")

    # 6. Cleanup (Delete from Drive)
    # Only delete tiles that were successfully processed
    if processed_tile_ids:
        delete_from_gdrive(processed_tile_ids)
    
    # Local cleanup
    setup_batch_dirs() # Wipes temp folders

    return processed_tile_ids

def delete_from_gdrive(tile_ids):
    """Delete processed tiles from Google Drive."""
    print(f"\nDeleting {len(tile_ids)} tiles from Google Drive...")
    
    # Get all files first to find matches
    result = subprocess.run(
        ['rclone', 'lsf', f'{RCLONE_REMOTE}:{GDRIVE_FOLDER}'],
        capture_output=True, text=True
    )
    
    files_to_delete = []
    tile_set = set(tile_ids)
    
    for line in result.stdout.splitlines():
        tid = tile_id_from_name(line)
        if tid is not None and tid in tile_set:
            files_to_delete.append(line.strip())

    if not files_to_delete:
        return

    # Delete files one by one (safer than glob)
    for i, f in enumerate(files_to_delete, 1):
        if i % 10 == 0: print(f"  Deleting {i}/{len(files_to_delete)}...", end='\r')
        subprocess.run(['rclone', 'delete', f'{RCLONE_REMOTE}:{GDRIVE_FOLDER}/{f}'], capture_output=True)
    
    subprocess.run(['rclone', 'cleanup', f'{RCLONE_REMOTE}:'], capture_output=True)
    print(f"\n✓ Drive cleaned ({len(files_to_delete)} files)")

# --- KEEPING ORIGINAL EXPORT/GEN FUNCTIONS ---

def generate_arid_tiles():
    """Generate list of all arid tile IDs (same as original)."""
    if os.path.exists('arid_tile_ids.json'):
        print("Loading cached arid tile IDs...")
        with open('arid_tile_ids.json', 'r') as f: return json.load(f)
    
    print("Error: arid_tile_ids.json not found. Please run your original script once to generate it.")
    return []

def generate_tile_bbox(tile_id):
    AFRICA_BBOX = [-17.6, -35.0, 51.4, 37.3]
    GRID_SIZE = 2.0
    lat_steps = int((AFRICA_BBOX[3] - AFRICA_BBOX[1]) / GRID_SIZE) + 1
    row = tile_id // lat_steps
    col = tile_id % lat_steps
    lon = AFRICA_BBOX[0] + row * GRID_SIZE
    lat = AFRICA_BBOX[1] + col * GRID_SIZE
    return [lon, lat, min(lon + GRID_SIZE, AFRICA_BBOX[2]), min(lat + GRID_SIZE, AFRICA_BBOX[3])]

def export_tiles_from_gee(tile_ids):
    """Export tiles from GEE to Google Drive."""
    try:
        ee.Initialize()
    except Exception as e:
        print(f"ERROR: Earth Engine Init failed: {e}")
        return [], [], []
    
    print(f"\nExporting {len(tile_ids)} tiles from GEE...")
    successful, skipped, failed = [], [], []
    
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
            
            if collection.size().getInfo() == 0:
                print("⚠ No images")
                skipped.append(tile_id)
                continue
            
            composite = collection.median().clip(geometry)
            desc = f"africa_s2_2021_tile_{tile_id:04d}"
            
            ee.batch.Export.image.toDrive(
                image=composite, description=desc, folder=GDRIVE_FOLDER,
                fileNamePrefix=desc, region=geometry, scale=10,
                crs='EPSG:4326', fileFormat='GeoTIFF', maxPixels=1e13
            ).start()
            print("✓")
            successful.append(tile_id)
        except Exception as e:
            print(f"✗ {e}")
            failed.append(tile_id)
            
    return successful, skipped, failed

def main():
    print("="*80)
    print("Africa CPI Detection - Master Pipeline (Refactored)")
    print("="*80)
    
    state = initialize_state()
    
    # 1. Arid Tiles
    if not state['arid_tiles']:
        state['arid_tiles'] = generate_arid_tiles()
        save_state(state)
        if not state['arid_tiles']: return
    
    # 2. Sync Drive
    state['in_gdrive'] = check_gdrive_contents()
    save_state(state)
    
    # 3. Logic
    arid_set = set(state['arid_tiles'])
    processed_set = set(state['processed_tiles'])
    in_gdrive_set = set(state['in_gdrive'])
    
    ready_to_process = list(in_gdrive_set - processed_set)
    need_export = list(arid_set - processed_set - in_gdrive_set)
    
    print(f"\nStatus:")
    print(f"  Ready to process: {len(ready_to_process)}")
    print(f"  Need export:      {len(need_export)}")
    
    # 4. Process Phase
    if ready_to_process:
        batch = sorted(ready_to_process)[:BATCH_SIZE_PROCESS]
        try:
            # Pass the list of IDs directly
            processed = process_tiles_with_copy(batch)
            if processed:
                state['processed_tiles'].extend(processed)
                state['processed_tiles'] = list(set(state['processed_tiles']))
                save_state(state)
                print(f"\n✓ Batch finished: {len(processed)} tiles processed.")
        except RuntimeError as e:
            print(f"\nCRITICAL ERROR: {e}")
            print("Pipeline stopped to prevent errors from compounding.")
            exit(1) # Hard stop

    # 5. Export Phase (Only if detection didn't fail)
    # Re-check drive contents after processing/deleting
    current_drive_count = len(check_gdrive_contents())
    
    if need_export and current_drive_count < MAX_GDRIVE_TILES:
        space = MAX_GDRIVE_TILES - current_drive_count
        to_export = min(BATCH_SIZE_EXPORT, space)
        if to_export > 0:
            batch_export = sorted(need_export)[:to_export]
            success, skipped, failed = export_tiles_from_gee(batch_export)
            state['exported_tiles'].extend(success)
            state['failed_tiles'].extend(skipped + failed)
            save_state(state)
    elif len(need_export) > 0:
        print("\nDrive full or no export needed. Waiting for processing.")

if __name__ == '__main__':
    main()