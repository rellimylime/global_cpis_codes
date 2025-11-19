"""
Simple Sentinel-2 downloader using sentinelsat (Copernicus API)

This is easier to set up than Google Earth Engine.

Setup:
1. Install: pip install sentinelsat
2. Create free account at: https://dataspace.copernicus.eu/
3. Edit the configuration below with your username/password
4. Run: python download_sentinel2_simple.py
"""

from sentinelsat import SentinelAPI, read_geojson, geojson_to_wkt
from datetime import date
import os
import zipfile
from osgeo import gdal
import numpy as np

# ============ CONFIGURATION ============
# Create account at: https://dataspace.copernicus.eu/

USERNAME = 'your_username_here'  # Replace with your Copernicus username
PASSWORD = 'your_password_here'  # Replace with your Copernicus password

# Define your area of interest
# Option 1: Bounding box [min_lon, min_lat, max_lon, max_lat]
# Example for a small area in Central Africa
MIN_LON, MIN_LAT, MAX_LON, MAX_LAT = 16.0, 0.5, 17.0, 1.5

# Date range (2021)
START_DATE = date(2021, 6, 1)
END_DATE = date(2021, 8, 31)

# Cloud coverage threshold (0-100)
MAX_CLOUD_COVER = 20

# Maximum number of products to download
MAX_PRODUCTS = 3

# Output directory
OUTPUT_DIR = 'imgs'

# =======================================


def download_sentinel2():
    """Download Sentinel-2 images."""

    print("=" * 80)
    print("Sentinel-2 Simple Downloader")
    print("=" * 80)

    if USERNAME == 'your_username_here':
        print("\nERROR: Please edit the script and add your Copernicus credentials!")
        print("Create account at: https://dataspace.copernicus.eu/")
        return

    # Connect to API
    print("\nConnecting to Copernicus API...")
    api = SentinelAPI(USERNAME, PASSWORD, 'https://catalogue.dataspace.copernicus.eu/resto')

    # Define area of interest (footprint)
    footprint = f"POLYGON(({MIN_LON} {MIN_LAT},{MAX_LON} {MIN_LAT},{MAX_LON} {MAX_LAT},{MIN_LON} {MAX_LAT},{MIN_LON} {MIN_LAT}))"

    print(f"\nSearching for products...")
    print(f"  Area: {MIN_LON}, {MIN_LAT} to {MAX_LON}, {MAX_LAT}")
    print(f"  Dates: {START_DATE} to {END_DATE}")
    print(f"  Max cloud cover: {MAX_CLOUD_COVER}%")

    # Search for products
    products = api.query(
        footprint,
        date=(START_DATE, END_DATE),
        platformname='Sentinel-2',
        producttype='S2MSI2A',  # Level-2A (atmospherically corrected)
        cloudcoverpercentage=(0, MAX_CLOUD_COVER)
    )

    print(f"\nFound {len(products)} products")

    if len(products) == 0:
        print("\nNo products found! Try:")
        print("  - Expanding date range")
        print("  - Increasing MAX_CLOUD_COVER")
        print("  - Making area smaller")
        return

    # Convert to DataFrame for easier handling
    products_df = api.to_dataframe(products)
    products_df = products_df.sort_values('cloudcoverpercentage')

    # Limit number of products
    products_df = products_df.head(MAX_PRODUCTS)

    print(f"\nDownloading {len(products_df)} products (least cloudy)...")
    print("-" * 80)

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Download products
    for idx, (product_id, product_info) in enumerate(products_df.iterrows()):
        print(f"\nProduct {idx + 1}/{len(products_df)}:")
        print(f"  Title: {product_info['title']}")
        print(f"  Date: {product_info['beginposition']}")
        print(f"  Cloud cover: {product_info['cloudcoverpercentage']:.1f}%")
        print(f"  Size: {product_info['size']}")

        # Download
        print("  Downloading...")
        api.download(product_id, directory_path=OUTPUT_DIR)

    print("\n" + "=" * 80)
    print("Download complete!")
    print("=" * 80)
    print(f"\nProducts saved to: {OUTPUT_DIR}/")
    print("\nNext steps:")
    print("1. Unzip the .zip files")
    print("2. Extract and stack the bands (B04, B03, B02, B08)")
    print("3. Run: python demo.py")
    print("\nOr use the process_sentinel2_products.py script to automate step 2")


if __name__ == '__main__':
    download_sentinel2()
