"""
Download, process, and delete tiles in batches to save storage.
"""
import os
import subprocess
import shutil

def download_batch(batch_size=5):
    """Download next N tiles from Google Drive."""
    print(f"\n{'='*80}")
    print(f"Downloading next {batch_size} base tiles...")
    print(f"{'='*80}")
    
    # Each base tile = 4 chunks
    num_files = batch_size * 4
    
    # Use the existing download script
    import subprocess
    subprocess.run(f'python download_tiles_batch.py --batch-size {num_files}', shell=True)
    
    print(f"✓ Download complete")


def filter_and_copy():
    """Filter to arid regions and copy to imgs/."""
    print(f"\n{'='*80}")
    print("Filtering to arid regions...")
    print(f"{'='*80}")
    
    subprocess.run('python filter_arid_tiles.py', shell=True)


def process_tiles():
    """Run detection on tiles in imgs/."""
    print(f"\n{'='*80}")
    print("Processing tiles...")
    print(f"{'='*80}")
    
    # Count tiles
    tiles = [f for f in os.listdir('imgs') if f.endswith('.tif')]
    print(f"Found {len(tiles)} tiles to process")
    
    if len(tiles) == 0:
        print("No tiles to process")
        return False
    
    subprocess.run('python batch_detect_africa.py', shell=True, input=b'yes\n')
    return True


def cleanup():
    """Delete source tiles to free space."""
    print(f"\n{'='*80}")
    print("Cleaning up to free space...")
    print(f"{'='*80}")
    
    # Delete downloaded tiles
    download_dir = os.path.expanduser('~/Downloads/Africa_CPI_Sentinel2')
    if os.path.exists(download_dir):
        for f in os.listdir(download_dir):
            if f.endswith('.tif'):
                os.remove(os.path.join(download_dir, f))
        print(f"✓ Deleted tiles from {download_dir}")
    
    # Delete from imgs/
    if os.path.exists('imgs'):
        for f in os.listdir('imgs'):
            if f.endswith('.tif'):
                os.remove(os.path.join('imgs', f))
        print(f"✓ Deleted tiles from imgs/")
    
    # Keep results in result_africa/
    print(f"✓ Results preserved in result_africa/")


def main():
    """Run incremental processing loop."""
    
    BATCH_SIZE = 5  # Process 5 base tiles at a time (~30 GB)
    
    print("="*80)
    print("Incremental Africa CPI Processing")
    print("="*80)
    print(f"\nBatch size: {BATCH_SIZE} tiles (~{BATCH_SIZE * 6} GB)")
    print("\nThis will:")
    print("1. Download batch from Google Drive")
    print("2. Filter to arid regions")
    print("3. Process tiles")
    print("4. Delete source tiles (keep results)")
    print("5. Repeat until done")
    
    response = input("\nContinue? (yes/no): ")
    if response.lower() != 'yes':
        print("Cancelled.")
        return
    
    batch_num = 1
    
    while True:
        print(f"\n\n{'#'*80}")
        print(f"# BATCH {batch_num}")
        print(f"{'#'*80}\n")
        
        # Step 1: Download
        download_batch(BATCH_SIZE)
        
        # Step 2: Filter and copy
        filter_and_copy()
        
        # Check if we have tiles
        tiles = [f for f in os.listdir('imgs') if f.endswith('.tif')]
        if len(tiles) == 0:
            print("\n✓ No more tiles to process - DONE!")
            break
        
        # Step 3: Process
        processed = process_tiles()
        
        if not processed:
            break
        
        # Step 4: Cleanup
        cleanup()
        
        # Ask to continue
        response = input("\nProcess next batch? (yes/no/auto): ")
        if response.lower() == 'no':
            break
        elif response.lower() == 'auto':
            print("Auto mode - will continue automatically")
            batch_num += 1
            continue
        
        batch_num += 1
    
    print("\n" + "="*80)
    print("PROCESSING COMPLETE")
    print("="*80)
    print(f"\nResults in: result_africa/")
    print(f"\nTo create final shapefile:")
    print(f"  python merge_africa_results.py")


if __name__ == '__main__':
    main()