"""
Configuration for running CPI detection on HPC.

Edit these paths for your HPC environment.
"""

import os

# === HPC PATHS ===

# Where to store downloaded tiles from Google Drive
# Use /scratch or high-performance storage, NOT home directory
TILE_STORAGE = '/scratch/username/africa_tiles'

# Where to store processing results
RESULT_STORAGE = '/scratch/username/cpi_results'

# Temporary working directory
TEMP_STORAGE = '/scratch/username/temp'

# === PROCESSING OPTIONS ===

# Batch size for processing (adjust based on available disk space)
BATCH_SIZE = 20  # Process 20 tiles at a time

# Number of parallel workers (if using GPU, usually 1)
NUM_WORKERS = 1

# Use GPU if available
USE_GPU = True

# === GOOGLE DRIVE ===

# Google Drive folder name (where GEE exports tiles)
GEE_EXPORT_FOLDER = 'Africa_CPI_Sentinel2'

# rclone remote name (from rclone config)
RCLONE_REMOTE = 'gdrive'

# === HELPER FUNCTIONS ===

def setup_directories():
    """Create necessary directories if they don't exist."""
    for path in [TILE_STORAGE, RESULT_STORAGE, TEMP_STORAGE]:
        os.makedirs(path, exist_ok=True)
        print(f"✓ Directory ready: {path}")


def get_rclone_command():
    """Get rclone command to download tiles from Google Drive."""
    return f"rclone copy {RCLONE_REMOTE}:{GEE_EXPORT_FOLDER} {TILE_STORAGE}/ --progress"


if __name__ == '__main__':
    print("HPC Configuration:")
    print(f"  Tiles: {TILE_STORAGE}")
    print(f"  Results: {RESULT_STORAGE}")
    print(f"  Temp: {TEMP_STORAGE}")
    print(f"  Google Drive folder: {GEE_EXPORT_FOLDER}")
    print()
    print("To download tiles from Google Drive:")
    print(f"  {get_rclone_command()}")
    print()
    setup_directories()
