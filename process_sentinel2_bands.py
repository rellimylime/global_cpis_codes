"""
Process downloaded Sentinel-2 products into 4-band GeoTIFF for CPI detection.

This script:
1. Finds Sentinel-2 .SAFE folders or unzipped products
2. Extracts the required bands: B04 (Red), B03 (Green), B02 (Blue), B08 (NIR)
3. Stacks them into a single 4-band GeoTIFF
4. Saves to imgs/ directory ready for demo.py

Usage:
    python process_sentinel2_bands.py /path/to/downloaded/sentinel2/products
"""

import os
import sys
from osgeo import gdal
import numpy as np
from glob import glob

gdal.UseExceptions()


def find_band_file(product_dir, band_name, resolution='10m'):
    """Find the file path for a specific band in a Sentinel-2 product."""

    # Pattern for L2A products: .../GRANULE/.../IMG_DATA/R10m/*_B0X_10m.jp2
    pattern = f"{product_dir}/GRANULE/*/IMG_DATA/R{resolution}/*_{band_name}_{resolution}.jp2"
    files = glob(pattern)

    if files:
        return files[0]

    # Alternative pattern for older products
    pattern = f"{product_dir}/GRANULE/*/IMG_DATA/*_{band_name}.jp2"
    files = glob(pattern)

    if files:
        return files[0]

    return None


def stack_bands(product_dir, output_file):
    """Stack R-G-B-NIR bands into a single 4-band GeoTIFF."""

    print(f"\nProcessing: {os.path.basename(product_dir)}")

    # Find band files
    bands = {
        'B04': 'Red',
        'B03': 'Green',
        'B02': 'Blue',
        'B08': 'NIR'
    }

    band_files = {}
    for band_code, band_name in bands.items():
        filepath = find_band_file(product_dir, band_code)
        if filepath:
            band_files[band_code] = filepath
            print(f"  Found {band_name} ({band_code}): {os.path.basename(filepath)}")
        else:
            print(f"  ERROR: {band_name} ({band_code}) not found!")
            return False

    if len(band_files) != 4:
        print("  ERROR: Not all bands found!")
        return False

    # Read bands in order: R, G, B, NIR
    band_order = ['B04', 'B03', 'B02', 'B08']

    # Get dimensions from first band
    first_band = gdal.Open(band_files[band_order[0]])
    cols = first_band.RasterXSize
    rows = first_band.RasterYSize
    geotransform = first_band.GetGeoTransform()
    projection = first_band.GetProjection()

    print(f"  Dimensions: {cols} x {rows}")
    print(f"  Stacking bands...")

    # Create output file
    driver = gdal.GetDriverByName('GTiff')
    outds = driver.Create(
        output_file,
        cols,
        rows,
        4,  # 4 bands
        gdal.GDT_UInt16,
        options=['COMPRESS=LZW', 'TILED=YES']
    )

    outds.SetGeoTransform(geotransform)
    outds.SetProjection(projection)

    # Write each band
    for i, band_code in enumerate(band_order, 1):
        print(f"    Writing band {i}/4 ({band_code})...", end=' ')

        ds = gdal.Open(band_files[band_code])
        band_data = ds.GetRasterBand(1).ReadAsArray()

        outband = outds.GetRasterBand(i)
        outband.WriteArray(band_data)
        outband.SetDescription(band_code)
        outband.FlushCache()

        print("done")

        ds = None

    outds = None
    first_band = None

    print(f"  Saved: {output_file}")
    return True


def process_all_products(input_dir, output_dir='imgs'):
    """Process all Sentinel-2 products in a directory."""

    print("=" * 80)
    print("Sentinel-2 Band Stacker for CPI Detection")
    print("=" * 80)

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Find all .SAFE directories (Sentinel-2 product format)
    safe_dirs = glob(f"{input_dir}/**/*.SAFE", recursive=True)

    # Also check for already extracted directories
    if not safe_dirs:
        # Look for directories with GRANULE subdirectory
        for root, dirs, files in os.walk(input_dir):
            if 'GRANULE' in dirs:
                safe_dirs.append(root)

    if not safe_dirs:
        print(f"\nNo Sentinel-2 products found in: {input_dir}")
        print("\nExpected structure: *.SAFE/GRANULE/*/IMG_DATA/...")
        print("\nMake sure to unzip downloaded .zip files first!")
        return

    print(f"\nFound {len(safe_dirs)} Sentinel-2 product(s)")

    # Process each product
    success_count = 0
    for product_dir in safe_dirs:
        product_name = os.path.basename(product_dir).replace('.SAFE', '')

        # Generate output filename
        output_file = os.path.join(output_dir, f"{product_name}.tif")

        if os.path.exists(output_file):
            print(f"\nSkipping {product_name} (already processed)")
            continue

        if stack_bands(product_dir, output_file):
            success_count += 1

    print("\n" + "=" * 80)
    print("Processing complete!")
    print("=" * 80)
    print(f"\nProcessed: {success_count}/{len(safe_dirs)} products")
    print(f"Output directory: {output_dir}/")
    print("\nNext step: Run the CPI detection model")
    print("  python demo.py")


def main():
    if len(sys.argv) < 2:
        print("Usage: python process_sentinel2_bands.py <input_directory>")
        print("\nExample:")
        print("  python process_sentinel2_bands.py ./downloaded_sentinel2")
        print("\nOr edit OUTPUT_DIR in download script to point directly to ./imgs")
        sys.exit(1)

    input_dir = sys.argv[1]

    if not os.path.exists(input_dir):
        print(f"ERROR: Directory not found: {input_dir}")
        sys.exit(1)

    process_all_products(input_dir)


if __name__ == '__main__':
    main()
