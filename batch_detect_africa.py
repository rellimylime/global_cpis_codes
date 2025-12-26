import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import warnings
warnings.filterwarnings('ignore', category=UserWarning)
warnings.filterwarnings('ignore', category=FutureWarning)

from osgeo import gdal
gdal.UseExceptions()

from tools.detect_scripts import detect_sentinel_batch
import geopandas as gpd
from shapely.geometry import box
import re
import json
from datetime import datetime


def load_processing_progress():
    """Load record of which tiles have been processed."""
    progress_file = 'africa_detection_progress.json'
    
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            return json.load(f)
    
    return {
        'completed_tiles': [],
        'failed_tiles': [],
        'total_completed': 0,
        'processing_history': []
    }


def save_processing_progress(progress):
    """Save processing progress."""
    with open('africa_detection_progress.json', 'w') as f:
        json.dump(progress, f, indent=2)


def extract_tile_bbox(filename):
    """Extract bounding box from tile filename or metadata."""
    match = re.search(r'tile_(\d+)', filename)
    if not match:
        return None
    
    tile_id = int(match.group(1))
    
    metadata_files = [
        'africa_tiles_2021_metadata.json',
        'africa_tiles_2021_batch_1.json',
        'gee_export_progress.json'
    ]
    
    for meta_file in metadata_files:
        if os.path.exists(meta_file):
            with open(meta_file, 'r') as f:
                data = json.load(f)
                tiles = data.get('tiles', [])
                for tile in tiles:
                    if tile['id'] == tile_id:
                        return tile['bbox']
    return None


def filter_arid_tiles(img_list, shapefile_path='Africa_Arid_Regions_All-shp'):
    """Filter image list to only those in arid regions."""
    print("\nFiltering tiles to arid regions only...")
    
    # Load arid regions
    arid_gdf = gpd.read_file(shapefile_path)
    if arid_gdf.crs != 'EPSG:4326':
        arid_gdf = arid_gdf.to_crs('EPSG:4326')
    
    arid_union = arid_gdf.union_all()
    
    filtered = []
    skipped = []
    
    for img_file in img_list:
        filename = os.path.basename(img_file)
        bbox = extract_tile_bbox(filename)
        
        if bbox is None:
            filtered.append(img_file)
            continue
        
        tile_poly = box(bbox[0], bbox[1], bbox[2], bbox[3])
        
        if tile_poly.intersects(arid_union):
            filtered.append(img_file)
        else:
            skipped.append(filename)
    
    if skipped:
        print(f"  Skipped {len(skipped)} tiles outside arid regions")
    
    print(f"  {len(filtered)} tiles in arid regions")
    
    return filtered


def main():
    """Run CPI detection on images in imgs/ directory."""
    
    BATCH_SIZE = 50  # Process this many tiles at a time

    print("=" * 80)
    print("Batch CPI Detection for Africa")
    print("=" * 80)

    # Load processing progress
    progress = load_processing_progress()
    completed = set(progress['completed_tiles'])
    
    if completed:
        print(f"\n✓ Found {len(completed)} previously completed tiles")

    # Model configuration
    model_cfg = dict(
        cfg_file="model/cascade_mask_rcnn_pointrend_cbam.py",
        checkpoint="model/cascade_mask_rcnn_pointrend_cbam.pth",
    )

    preprocess_cfg = dict(
        ref_dataset_json="model/ann.json",
    )

    result_merge_cfg = dict(
        nms_thr=0.1,
        nms_merge_cats=True,
        score_thr=[0.3, 0.85],
    )

    # Input/output directories
    ori_img_dir = "imgs"
    workdir = "temp"
    seg_res_path = "result_africa"

    # Check if images exist
    if not os.path.exists(ori_img_dir):
        print(f"\nERROR: Directory not found: {ori_img_dir}")
        return

    all_img_files = [os.path.join(ori_img_dir, f) for f in os.listdir(ori_img_dir) if f.endswith('.tif')]

    if len(all_img_files) == 0:
        print(f"\nERROR: No .tif files found in {ori_img_dir}/")
        return

    # Filter to arid regions
    img_list = filter_arid_tiles(all_img_files)
    
    # Skip already completed
    img_list = [img for img in img_list if os.path.basename(img) not in completed]

    if len(img_list) == 0:
        print("\n✓ All tiles already processed!")
        return

    # Limit to batch size
    total_remaining = len(img_list)
    img_list = img_list[:BATCH_SIZE]

    print(f"\n{'='*80}")
    print("PROCESSING STATUS")
    print(f"{'='*80}")
    print(f"Already completed: {len(completed)}")
    print(f"Remaining in imgs/: {total_remaining}")
    print(f"This batch: {len(img_list)}")
    print(f"Estimated time: ~{len(img_list) * 9 / 60:.1f} hours")

    response = input("\nContinue? (yes/no): ")
    if response.lower() != 'yes':
        print("Cancelled.")
        return

    print("\n" + "=" * 80)
    print("Starting detection...")
    print("=" * 80)

    # Track this batch
    batch_start = len(progress['processing_history']) + 1
    batch_tiles = [os.path.basename(f) for f in img_list]

    # Run detection
    try:
        detect_sentinel_batch(
            ori_img_dir=ori_img_dir,
            img_list_file=batch_tiles,
            workdir=workdir,
            seg_res_path=seg_res_path,
            model_cfg=model_cfg,
            **preprocess_cfg,
            **result_merge_cfg,
        )
        
        # Mark as completed
        progress['completed_tiles'].extend(batch_tiles)
        progress['total_completed'] = len(progress['completed_tiles'])
        progress['processing_history'].append({
            'batch': batch_start,
            'tiles': batch_tiles,
            'count': len(batch_tiles),
            'timestamp': datetime.now().isoformat()
        })
        
        save_processing_progress(progress)
        
        print("\n" + "=" * 80)
        print("✓ Batch Complete!")
        print("=" * 80)
        print(f"Processed: {len(batch_tiles)} tiles")
        print(f"Total completed: {progress['total_completed']}")
        print(f"Remaining: {total_remaining - len(batch_tiles)}")
        
    except Exception as e:
        print(f"\n✗ Error during processing: {e}")
        return

    print(f"\nResults saved to: {seg_res_path}/")
    
    if total_remaining > len(img_list):
        print(f"\n{total_remaining - len(img_list)} tiles remaining in imgs/")
        print("Run again to process next batch")


if __name__ == '__main__':
    main()