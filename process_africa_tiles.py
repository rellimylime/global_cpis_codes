"""
Track and process Africa tiles systematically.

This script:
1. Scans Google Drive folder or Downloads for Africa tiles
2. Tracks which tiles have been processed
3. Moves unprocessed tiles to imgs/ in batches
4. Runs detection on each batch
5. Creates a progress report

Usage:
    python process_africa_tiles.py [--batch-size 10] [--source /path/to/tiles]
"""

import os
import sys
import json
import shutil
from datetime import datetime
import argparse


def find_tiles(source_dir):
    """Find all Africa tiles in source directory."""
    tiles = []

    if not os.path.exists(source_dir):
        print(f"ERROR: Source directory not found: {source_dir}")
        return tiles

    for filename in os.listdir(source_dir):
        if filename.startswith('africa_s2_') and filename.endswith('.tif'):
            tiles.append({
                'filename': filename,
                'path': os.path.join(source_dir, filename),
                'size_mb': os.path.getsize(os.path.join(source_dir, filename)) / (1024*1024)
            })

    return sorted(tiles, key=lambda x: x['filename'])


def load_progress():
    """Load processing progress from JSON file."""
    progress_file = 'africa_processing_progress.json'

    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            return json.load(f)

    return {
        'processed': [],
        'failed': [],
        'in_progress': [],
        'total_tiles': 0,
        'last_updated': None
    }


def save_progress(progress):
    """Save processing progress to JSON file."""
    progress['last_updated'] = datetime.now().isoformat()

    with open('africa_processing_progress.json', 'w') as f:
        json.dump(progress, f, indent=2)


def get_tile_id(filename):
    """Extract tile ID from filename."""
    # Example: africa_s2_2021_tile_0042.tif -> 42
    try:
        parts = filename.replace('.tif', '').split('_')
        return int(parts[-1])
    except:
        return None


def move_batch_to_imgs(tiles, batch_size, imgs_dir='imgs'):
    """Move a batch of tiles to imgs/ directory."""
    moved = []

    for i, tile in enumerate(tiles):
        if i >= batch_size:
            break

        dest = os.path.join(imgs_dir, tile['filename'])

        try:
            shutil.copy2(tile['path'], dest)
            moved.append(tile['filename'])
            print(f"  ✓ Copied: {tile['filename']}")
        except Exception as e:
            print(f"  ✗ Failed to copy {tile['filename']}: {e}")

    return moved


def check_processing_results(filenames, result_dir='result_africa'):
    """Check which tiles have been successfully processed."""
    processed = []
    failed = []

    for filename in filenames:
        tile_name = filename.replace('.tif', '')
        result_path = os.path.join(result_dir, tile_name)

        if os.path.exists(result_path) and os.listdir(result_path):
            processed.append(filename)
        else:
            failed.append(filename)

    return processed, failed


def main():
    parser = argparse.ArgumentParser(description='Process Africa tiles systematically')
    parser.add_argument('--source', default=os.path.expanduser('~/Downloads'),
                       help='Source directory containing Africa tiles')
    parser.add_argument('--batch-size', type=int, default=10,
                       help='Number of tiles to process per batch')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without doing it')

    args = parser.parse_args()

    print("=" * 80)
    print("Africa Tiles Processing Tracker")
    print("=" * 80)

    # Find all tiles
    print(f"\n1. Scanning for tiles in: {args.source}")
    all_tiles = find_tiles(args.source)

    if not all_tiles:
        print(f"\n  No tiles found in {args.source}")
        print("\n  Tips:")
        print("  - Check if tiles are in a subfolder (e.g., ~/Downloads/Africa_CPI_Sentinel2/)")
        print("  - Specify source with: --source /path/to/tiles")
        print(f"  - Tiles should be named like: africa_s2_2021_tile_XXXX.tif")
        return

    print(f"  Found {len(all_tiles)} tiles")

    # Load progress
    progress = load_progress()

    # Check which are already processed
    print(f"\n2. Checking processing status...")
    processed_tiles = set(progress['processed'])

    # Also check result_africa directory
    if os.path.exists('result_africa'):
        for dirname in os.listdir('result_africa'):
            processed_tiles.add(dirname + '.tif')

    # Find unprocessed tiles
    unprocessed = [t for t in all_tiles if t['filename'] not in processed_tiles]

    print(f"  Already processed: {len(processed_tiles)}")
    print(f"  Remaining: {len(unprocessed)}")

    if len(unprocessed) == 0:
        print("\n✓ All tiles have been processed!")
        return

    # Show next batch
    batch_size = min(args.batch_size, len(unprocessed))
    next_batch = unprocessed[:batch_size]

    print(f"\n3. Next batch to process ({batch_size} tiles):")
    total_size = 0
    for i, tile in enumerate(next_batch, 1):
        tile_id = get_tile_id(tile['filename'])
        print(f"  {i}. Tile {tile_id:04d}: {tile['filename']} ({tile['size_mb']:.1f} MB)")
        total_size += tile['size_mb']

    print(f"\n  Total batch size: {total_size:.1f} MB")

    if args.dry_run:
        print("\n[DRY RUN] - No files will be moved or processed")
        return

    # Ask for confirmation
    print("\n" + "=" * 80)
    response = input(f"Move these {batch_size} tiles to imgs/ and process? (yes/no): ")

    if response.lower() != 'yes':
        print("Cancelled.")
        return

    # Move files
    print(f"\n4. Moving tiles to imgs/...")
    moved = move_batch_to_imgs(next_batch, batch_size)

    print(f"\n  Moved {len(moved)} tiles to imgs/")

    # Update progress
    progress['in_progress'] = moved
    progress['total_tiles'] = len(all_tiles)
    save_progress(progress)

    print("\n" + "=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print("\n5. Run detection:")
    print("   python batch_detect_africa.py")
    print("\n6. After detection completes, run this script again:")
    print("   python process_africa_tiles.py")
    print("\n7. Results will be in result_africa/")

    print("\n" + "=" * 80)
    print("PROGRESS SUMMARY")
    print("=" * 80)
    print(f"\nTotal tiles: {len(all_tiles)}")
    print(f"Processed: {len(processed_tiles)}")
    print(f"In progress: {len(moved)}")
    print(f"Remaining: {len(unprocessed) - len(moved)}")

    percent_done = (len(processed_tiles) / len(all_tiles)) * 100
    print(f"\nCompletion: {percent_done:.1f}%")

    # Show which tile IDs we have
    tile_ids = sorted([get_tile_id(t['filename']) for t in all_tiles if get_tile_id(t['filename']) is not None])
    if tile_ids:
        print(f"\nTile IDs: {min(tile_ids)} to {max(tile_ids)}")
        print(f"(Note: Not all IDs may be present due to ocean filtering)")


if __name__ == '__main__':
    main()
