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
RAW_CACHE_DIR = 'imgs_cache_raw' # Cache for raw tiles 
SCALED_DIR = 'imgs_batch_u8' # Where combined/scaled u8 tiles go
SCALED_CACHE_DIR = 'imgs_cache_u8' # Cache for scaled tiles

BATCH_SIZE_EXPORT = 50   # Export 50 tiles at a time from GEE
BATCH_SIZE_PROCESS = 2  # Process 10 tiles at a time locally
MAX_GDRIVE_TILES = 100   # Keep max 100 tiles in GDrive (~50GB safety margin)

STATE_FILE = 'pipeline_state.json'
# =======================================

TILE_RE = re.compile(r"tile_(\d+)")
SPLIT_RE = re.compile(r"tile_(\d+)-(\d+)-(\d+)\.tif$")
NOSPLIT_RE = re.compile(r"tile_(\d+)\.tif$")

def tile_present(drive_files: list[str], tid: int) -> bool:
    """
    True if ANY Drive file exists for this tile id (split or non-split).
    Example matches:
      tile_0316.tif
      tile_0316-0-0.tif
      tile_0316-1-0.tif
    """
    pat = re.compile(rf"tile_{tid:04d}(\D|$)")
    return any(pat.search(name) for name in drive_files)


def tile_id_from_name(name: str):
    m = TILE_RE.search(name)
    return int(m.group(1)) if m else None

def list_drive_tifs() -> list[str]:
    r = subprocess.run(
        ["rclone", "lsf", f"{RCLONE_REMOTE}:{GDRIVE_FOLDER}", "--max-depth", "1"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        raise RuntimeError(f"rclone lsf failed:\n{r.stderr}")
    return [line.strip() for line in r.stdout.splitlines() if line.strip().endswith(".tif")]

def tile_complete(drive_files: list[str], tile_id: int) -> bool:
    # Complete if a non-split file exists
    for f in drive_files:
        m2 = NOSPLIT_RE.search(f)
        if m2 and int(m2.group(1)) == tile_id:
            return True

    # Otherwise, treat as complete if ANY split part exists.
    # This avoids waiting forever when EE uses an unexpected number of splits.
    for f in drive_files:
        m = SPLIT_RE.search(f)
        if m and int(m.group(1)) == tile_id:
            return True

    return False


def setup_batch_dirs():
    """Clear and recreate batch directories to prevent ghost files (Fix #2)."""
    if os.path.exists(RAW_DIR):
        shutil.rmtree(RAW_DIR)
    if os.path.exists(SCALED_DIR):
        shutil.rmtree(SCALED_DIR)
    os.makedirs(RAW_DIR)
    os.makedirs(SCALED_DIR)


def download_file(filename):
    subprocess.run([
        'rclone', 'copy',
        f'{RCLONE_REMOTE}:{GDRIVE_FOLDER}/{filename}',
        RAW_DIR,
        '--stats', '5s',
        '--stats-one-line'
    ], check=True)


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

    r = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)))
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
        for key in [
            'arid_tiles', 'exported_tiles',
            'processed_tiles', 'failed_tiles',
            'pending_export_tiles', 'pending_export_started_at'
        ]:
            if key not in state:
                state[key] = [] if key != 'pending_export_started_at' else None
        return state
    
    print("First run - creating new state file...")
    return {
        'arid_tiles': [],
        'exported_tiles': [],
        'processed_tiles': [],      # tile IDs only
        'failed_tiles': [],
        'pending_export_tiles': [], # tile IDs queued this batch
        'pending_export_started_at': None,
        'last_updated': None
    }

def save_state(state):
    state['last_updated'] = datetime.now().isoformat()
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def ensure_cache_dirs():
    os.makedirs(RAW_CACHE_DIR, exist_ok=True)
    os.makedirs(SCALED_CACHE_DIR, exist_ok=True)


def cache_raw_path(filename: str) -> str:
    return os.path.join(RAW_CACHE_DIR, filename)


def cache_scaled_path(out_name: str) -> str:
    return os.path.join(SCALED_CACHE_DIR, out_name)


def file_ok(path: str, min_bytes: int = 1024) -> bool:
    # cheap “not empty / not obviously broken” check
    return os.path.exists(path) and os.path.getsize(path) >= min_bytes

def delete_drive_files(filenames: list[str]) -> None:
    """
    Delete exact file objects from Drive. This avoids tile_id ambiguity.
    """
    if not filenames:
        return

    for i, name in enumerate(filenames, 1):
        print(f"  [{i}/{len(filenames)}] deleting {name}...", end=" ", flush=True)
        r = subprocess.run(
            ["rclone", "deletefile", f"{RCLONE_REMOTE}:{GDRIVE_FOLDER}/{name}"],
            capture_output=True, text=True
        )
        if r.returncode == 0:
            print("✓")
        else:
            print("✗")
            if r.stderr:
                print(r.stderr)

    # optional, but keeps Drive clean
    subprocess.run(["rclone", "cleanup", f"{RCLONE_REMOTE}:"], capture_output=True)

def process_tiles_with_copy(tile_ids_to_process):
    """
    Main processing logic with caching.
    - Keeps isolated batch dirs (RAW_DIR, SCALED_DIR) but avoids re-downloading/rescaling
      by using persistent caches (RAW_CACHE_DIR, SCALED_CACHE_DIR).
    """

    processed_files = []   # drive filenames successfully scaled and included in detection
    failed_files = []      # drive filenames that ultimately failed
    batch_list_files = []  # scaled filenames (local) written to _batch_list.txt


    print(f"\nProcessing batch of {len(tile_ids_to_process)} tiles...")

    ensure_cache_dirs()

    # 1) Clean workspace (batch dirs only)
    setup_batch_dirs()

    # 2) Map Tile IDs to Files in Drive
    print("Listing files in Drive to build file groups...")
    result = subprocess.run(
        ['rclone', 'lsf', f'{RCLONE_REMOTE}:{GDRIVE_FOLDER}'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"rclone lsf failed: {result.stderr}")

    files_by_tile = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.endswith(".tif"):
            continue
        tid = tile_id_from_name(line)
        if tid is not None and tid in tile_ids_to_process:
            files_by_tile.setdefault(tid, []).append(line)

    if not files_by_tile:
        print("No matching files found in Drive for this batch.")
        return []

    processed_tile_ids = []
    failed_tile_ids = []
    batch_list_files = []

    total_files = sum(len(v) for v in files_by_tile.values())
    print(f"Found files for {len(files_by_tile)} tiles ({total_files} files). Starting download/scale...")

    done_files = 0

    for tid, files in files_by_tile.items():
        tile_failed = False
        scaled_files_for_tile = []

        # stable order helps debugging
        files = sorted(files)

        for filename in files:
            done_files += 1
            print(f"  [{done_files}/{total_files}] tile {tid} file {filename}", flush=True)

            try:
                base, _ = os.path.splitext(filename)
                out_name = base + "_rgbnir_u8.tif"

                # ---- Step A: ensure raw in cache ----
                raw_cache = cache_raw_path(filename)
                if file_ok(raw_cache):
                    # copy cached raw into batch RAW_DIR
                    shutil.copy2(raw_cache, os.path.join(RAW_DIR, filename))
                    print("    raw: cache hit", flush=True)
                else:
                    print("    raw: downloading", flush=True)
                    download_file(filename)  # downloads into RAW_DIR

                    # validate and save to cache
                    raw_batch = os.path.join(RAW_DIR, filename)
                    if not file_ok(raw_batch):
                        raise RuntimeError("downloaded raw is missing/too small")
                    shutil.copy2(raw_batch, raw_cache)

                # ---- Step B: ensure scaled in cache ----
                scaled_cache = cache_scaled_path(out_name)
                scaled_batch = os.path.join(SCALED_DIR, out_name)

                if file_ok(scaled_cache):
                    shutil.copy2(scaled_cache, scaled_batch)
                    print("    u8: cache hit", flush=True)
                else:
                    print("    u8: scaling", flush=True)
                    out_name2 = scale_tile_to_u8(filename)  # reads RAW_DIR, writes SCALED_DIR
                    if out_name2 != out_name:
                        # safety, but should not happen with your scale fn
                        out_name = out_name2
                        scaled_batch = os.path.join(SCALED_DIR, out_name)

                    if not file_ok(scaled_batch):
                        raise RuntimeError("scaled output missing/too small")

                    shutil.copy2(scaled_batch, scaled_cache)

                scaled_files_for_tile.append(out_name)
                processed_files.append(filename)

            except Exception as e:
                # retry once: wipe batch raw and caches for this file, then redo
                print(f"    ⚠ error: {e}. Retrying once...", flush=True)
                try:
                    # wipe batch raw
                    local_raw = os.path.join(RAW_DIR, filename)
                    if os.path.exists(local_raw):
                        os.remove(local_raw)

                    # wipe cached raw and cached scaled (force fresh)
                    raw_cache = cache_raw_path(filename)
                    if os.path.exists(raw_cache):
                        os.remove(raw_cache)

                    base, _ = os.path.splitext(filename)
                    out_name = base + "_rgbnir_u8.tif"
                    scaled_cache = cache_scaled_path(out_name)
                    if os.path.exists(scaled_cache):
                        os.remove(scaled_cache)

                    # redownload + rescale
                    download_file(filename)
                    out_name2 = scale_tile_to_u8(filename)
                    if not file_ok(os.path.join(SCALED_DIR, out_name2)):
                        raise RuntimeError("retry scaled output missing/too small")

                    # save fresh into caches
                    shutil.copy2(os.path.join(RAW_DIR, filename), cache_raw_path(filename))
                    shutil.copy2(os.path.join(SCALED_DIR, out_name2), cache_scaled_path(out_name2))

                    scaled_files_for_tile.append(out_name2)
                    print("    ✓ retry success", flush=True)

                except Exception as final_e:
                    print(f"    ✗ failed after retry: {final_e}", flush=True)
                    tile_failed = True
                    failed_files.append(filename)
                    break

        if tile_failed:
            failed_tile_ids.append(tid)
        else:
            batch_list_files.extend(scaled_files_for_tile)
            processed_tile_ids.append(tid)

    if not batch_list_files:
        print("No files were successfully scaled.")
        return []

    # 4) Write _batch_list.txt
    list_path = os.path.join(SCALED_DIR, "_batch_list.txt")
    with open(list_path, "w") as fp:
        for name in batch_list_files:
            fp.write(name + "\n")

    # 5) Run Detection (make cwd explicit so model/ paths resolve)
    print(f"\nRunning Detection on {len(batch_list_files)} files...")
    cmd = ['python', 'batch_detect_africa.py', '--auto', '--img_dir', SCALED_DIR]
    repo_root = os.path.dirname(os.path.abspath(__file__))

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)

    print("--- Detection Output ---")
    print(result.stdout)
    if result.stderr:
        print(f"Errors: {result.stderr}")
    print("------------------------")

    if result.returncode != 0:
        raise RuntimeError("Detection script crashed! Stopping pipeline to prevent Drive overflow.")

    # 6) Cleanup drive and batch dirs
    # Delete only the exact Drive files we successfully processed
    if processed_files:
        delete_drive_files(processed_files)

    setup_batch_dirs()
    return processed_tile_ids

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
    """Export tiles from GEE to Google Drive.

    Returns:
      successful: tiles where task.start() succeeded
      skipped: tiles with no images available
      failed: tiles with real errors (not queue-full)
    """
    try:
        ee.Initialize()
    except Exception as e:
        print(f"ERROR: Earth Engine Init failed: {e}")
        return [], [], []

    print(f"\nExporting {len(tile_ids)} tiles from GEE...")
    successful, skipped, failed = [], [], []

    # Optional but recommended: avoid queuing exports that already exist in Drive.
    # This is fast and prevents duplicates when you re-run.
    try:
        drive_files = list_drive_tifs()  # uses rclone lsf --max-depth 1
        print(f"\nDrive tif count: {len(drive_files)}")
        print("Drive sample:", drive_files[:5])
        in_drive = set()
        for f in drive_files:
            tid = tile_id_from_name(f)
            if tid is not None:
                in_drive.add(tid)
    except Exception as e:
        # If rclone is flaky, don't block exports, just proceed.
        print(f"Warning: couldn't pre-check Drive contents ({e}). Proceeding anyway.")
        in_drive = set()

    for i, tile_id in enumerate(tile_ids, 1):
        # Skip if already present in Drive (single or split)
        if tile_id in in_drive:
            print(f"  [{i}/{len(tile_ids)}] Tile {tile_id}... already in Drive, skip")
            continue

        print(f"  [{i}/{len(tile_ids)}] Tile {tile_id}...", end=" ", flush=True)

        try:
            bbox = generate_tile_bbox(tile_id)
            geometry = ee.Geometry.Rectangle(bbox)

            collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                          .filterBounds(geometry)
                          .filterDate("2021-01-01", "2021-12-31")
                          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
                          .select(["B4", "B3", "B2", "B8"]))

            if collection.size().getInfo() == 0:
                print("⚠ No images")
                skipped.append(tile_id)
                continue

            composite = collection.median().clip(geometry)
            desc = f"africa_s2_2021_tile_{tile_id:04d}"

            task = ee.batch.Export.image.toDrive(
                image=composite,
                description=desc,
                folder=GDRIVE_FOLDER,
                fileNamePrefix=desc,
                region=geometry,
                scale=10,
                crs="EPSG:4326",
                fileFormat="GeoTIFF",
                maxPixels=1e13,
            )

            task.start()
            print("✓")
            successful.append(tile_id)

        except Exception as e:
            msg = str(e)

            # KEY FIX: if queue is full, stop immediately and DO NOT mark as failed
            if "Too many tasks already in the queue" in msg:
                print(f"✗ {msg}")
                print("Earth Engine queue is full. Stopping this export batch early.")
                break

            # Other errors are real failures
            print(f"✗ {msg}")
            failed.append(tile_id)

    return successful, skipped, failed


def main():
    print("="*80)
    print("Africa CPI Detection - Master Pipeline (Strict)")
    print("="*80)

    state = initialize_state()

    # 1) Load arid tiles list
    if not state['arid_tiles']:
        state['arid_tiles'] = generate_arid_tiles()
        save_state(state)
        if not state['arid_tiles']:
            return

    arid_set = set(int(x) for x in state['arid_tiles'])
    processed_set = set(int(x) for x in state['processed_tiles'])
    failed_set = set(int(x) for x in state['failed_tiles'])

    # Always read Drive file listing once per run
    drive_files = list_drive_tifs()

        # 0) Always process anything already complete in Drive first
    drive_tile_ids = sorted({tile_id_from_name(f) for f in drive_files if tile_id_from_name(f) is not None})

    ready_now = []
    for tid in drive_tile_ids:
        if tid in processed_set or tid in failed_set:
            continue
        if tile_complete(drive_files, tid):
            ready_now.append(tid)

    if ready_now:
        batch = ready_now[:BATCH_SIZE_PROCESS]
        print(f"\nFound {len(ready_now)} complete tiles in Drive. Processing {len(batch)} now...")
        processed_tile_ids = process_tiles_with_copy(batch)

        state['processed_tiles'] = sorted(set(state['processed_tiles']) | set(processed_tile_ids))
        save_state(state)
        return

    pending = state.get("pending_export_tiles", []) or []
    pending = [int(x) for x in pending]

    # 2) If a batch was queued earlier, do NOT export again
    if pending:
        arrived = []
        not_arrived = []
        complete = []
        incomplete = []

        for tid in pending:
            if tile_present(drive_files, tid):
                arrived.append(tid)
                if tile_complete(drive_files, tid):
                    complete.append(tid)
                else:
                    incomplete.append(tid)
            else:
                not_arrived.append(tid)

        print(f"\nPending export tiles: {len(pending)}")
        print(f"Arrived in Drive:     {len(arrived)}")
        print(f"Still exporting:      {len(not_arrived)}")
        print(f"Complete to process:  {len(complete)}")
        print(f"Incomplete in Drive:  {len(incomplete)}")

        # Wait until everything is BOTH arrived and complete
        if not_arrived or incomplete:
            return

        print("\nAll pending tiles are complete in Drive. Processing...")
        processed_tile_ids = process_tiles_with_copy(complete)

        state['processed_tiles'] = sorted(set(state['processed_tiles']) | set(processed_tile_ids))
        state['pending_export_tiles'] = []
        state['pending_export_started_at'] = None
        save_state(state)
        print(f"\n✓ Processed {len(processed_tile_ids)} tiles.")
        return


    # 3) No pending batch -> decide next export batch
    remaining = sorted(list(arid_set - processed_set - failed_set))
    if not remaining:
        print("\n✓ Nothing left to export/process.")
        return

    # Avoid exporting tiles already complete in Drive
    already_ready = set()
    for tid in remaining[:500]:  # cap for speed
        if tile_complete(drive_files, tid):
            already_ready.add(tid)

    remaining = [tid for tid in remaining if tid not in already_ready]

    if not remaining:
        print("\nSome tiles are already in Drive. Run again to process them.")
        return

    batch_export = remaining[:BATCH_SIZE_EXPORT]
    print(f"\nQueueing export batch of {len(batch_export)} tiles...")

    success, skipped, failed = export_tiles_from_gee(batch_export)

    # Record failures as tile IDs
    state['failed_tiles'] = sorted(set(state['failed_tiles']) | set(skipped) | set(failed))

    # IMPORTANT: pending batch is ONLY what successfully started
    state['pending_export_tiles'] = success[:]
    state['pending_export_started_at'] = datetime.now().isoformat()

    save_state(state)

    print("\nExport batch queued. Exiting now.")
    print("Next run will wait until these tiles are in Drive, then process them.")

if __name__ == '__main__':
    main()