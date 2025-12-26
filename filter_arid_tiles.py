# filter_arid_tiles.py
"""
Filter Africa tiles to only those overlapping with arid regions.
"""

import geopandas as gpd
from shapely.geometry import box
import os
import shutil
import re
import zipfile

def unzip_tiles(tiles_dir):
    """Unzip any .zip files in the tiles directory."""
    zip_files = [f for f in os.listdir(tiles_dir) if f.endswith('.zip')]
    
    if not zip_files:
        print("No zip files found.")
        return
    
    print(f"Found {len(zip_files)} zip files. Extracting...")
    
    for zip_file in zip_files:
        zip_path = os.path.join(tiles_dir, zip_file)
        print(f"  Extracting {zip_file}...")
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tiles_dir)
            print(f"    ✓ Extracted")
            
            # Optionally delete the zip after extraction
            # os.remove(zip_path)
            
        except Exception as e:
            print(f"    ✗ Error: {e}")

def extract_tile_bbox(filename):
    """Extract bounding box from tile filename or metadata."""
    # Tile names like: africa_s2_2021_tile_0148-0000000000-0000011776.tif
    # We need to get the tile ID and look it up in the metadata
    
    match = re.search(r'tile_(\d+)', filename)
    if not match:
        return None
    
    tile_id = int(match.group(1))
    
    # Load tile metadata from your export progress
    import json
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

def main():
    # Load arid regions shapefile
    print("Loading arid regions shapefile...")
    arid_gdf = gpd.read_file('Africa_Arid_Regions_All-shp')
    
    # Convert to EPSG:4326 once at the start
    if arid_gdf.crs != 'EPSG:4326':
        print(f"  Converting from {arid_gdf.crs} to EPSG:4326")
        arid_gdf = arid_gdf.to_crs('EPSG:4326')
    
    print(f"  Arid regions CRS: {arid_gdf.crs}")
    
    # Create a union of all arid regions once (more efficient)
    arid_union = arid_gdf.unary_union
    
    # Unzip any zip files first
    tiles_dir = os.path.expanduser('~/Downloads/Africa_CPI_Sentinel2')
    unzip_tiles(tiles_dir)
    
    # Get all tile files
    tile_files = [f for f in os.listdir(tiles_dir) if f.endswith('.tif')]
    
    print(f"\nFound {len(tile_files)} total tiles")
    
    # Filter tiles that overlap with arid regions
    overlapping_tiles = []
    
    for tile_file in tile_files:
        bbox = extract_tile_bbox(tile_file)
        if bbox is None:
            continue
        
        # Create tile polygon (already in EPSG:4326)
        tile_poly = box(bbox[0], bbox[1], bbox[2], bbox[3])
        
        # Check overlap directly (both in EPSG:4326 now)
        if tile_poly.intersects(arid_union):
            overlapping_tiles.append(tile_file)
    
    print(f"\n{len(overlapping_tiles)} tiles overlap with arid regions")
    print(f"Skipping {len(tile_files) - len(overlapping_tiles)} tiles")
    
    
    # Copy overlapping tiles to imgs/
    imgs_dir = 'imgs'
    os.makedirs(imgs_dir, exist_ok=True)
    
    # Clear imgs/ first
    for f in os.listdir(imgs_dir):
        if f.endswith('.tif'):
            os.remove(os.path.join(imgs_dir, f))
    
    print(f"\nCopying {len(overlapping_tiles)} tiles to imgs/...")
    for tile_file in overlapping_tiles:
        src = os.path.join(tiles_dir, tile_file)
        dst = os.path.join(imgs_dir, tile_file)
        shutil.copy2(src, dst)
        print(f"  ✓ {tile_file}")
    
    print(f"\n✓ Done! {len(overlapping_tiles)} tiles ready for processing")
    print(f"  Estimated time: ~{len(overlapping_tiles) * 9 / 60:.1f} hours")

if __name__ == '__main__':
    main()