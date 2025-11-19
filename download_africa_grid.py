"""
Download Sentinel-2 for ALL of Africa using a grid-based approach.

This script:
1. Divides Africa into manageable tiles (e.g., 1° x 1° grid)
2. Downloads best cloud-free image for each tile in 2021
3. Processes them into 4-band GeoTIFF ready for CPI detection

WARNING: This will download MANY images (potentially terabytes of data).
Start with a smaller region first to test!

Requirements:
- pip install requests oauthlib
- Copernicus Data Space account: https://dataspace.copernicus.eu/
"""

import requests
import json
import os
from datetime import datetime
import time

# ============ CONFIGURATION ============

USERNAME = 'your_username_here'
PASSWORD = 'your_password_here'

# Africa bounding box (approximate)
AFRICA_BBOX = [-17.6, -35.0, 51.4, 37.3]  # [min_lon, min_lat, max_lon, max_lat]

# Or define custom region (e.g., East Africa, Sahel, etc.)
# AFRICA_BBOX = [20.0, -12.0, 52.0, 18.0]  # East Africa example

# Grid size (degrees) - smaller = more tiles, more precise
# 1.0 = ~111km tiles, 2.0 = ~222km tiles
GRID_SIZE = 2.0

# Date range (2021)
START_DATE = '2021-01-01'
END_DATE = '2021-12-31'

# Cloud coverage threshold
MAX_CLOUD_COVER = 30  # Higher for Africa (clouds are common)

# Output directory
OUTPUT_DIR = 'africa_sentinel2'

# How many images per grid cell (usually 1 is enough - picks best)
IMAGES_PER_CELL = 1

# =======================================

AUTH_URL = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'
SEARCH_URL = 'https://catalogue.dataspace.copernicus.eu/odata/v1/Products'
DOWNLOAD_URL = 'https://zipper.dataspace.copernicus.eu/odata/v1/Products'


def get_access_token(username, password):
    """Get OAuth2 access token."""
    data = {
        'grant_type': 'password',
        'username': username,
        'password': password,
        'client_id': 'cdse-public'
    }
    try:
        response = requests.post(AUTH_URL, data=data)
        response.raise_for_status()
        return response.json()['access_token']
    except Exception as e:
        print(f"Authentication failed: {e}")
        return None


def create_grid(bbox, grid_size):
    """Create grid of tiles covering the bbox."""
    min_lon, min_lat, max_lon, max_lat = bbox

    tiles = []
    lon = min_lon
    while lon < max_lon:
        lat = min_lat
        while lat < max_lat:
            tile_bbox = [lon, lat, min(lon + grid_size, max_lon), min(lat + grid_size, max_lat)]
            tiles.append(tile_bbox)
            lat += grid_size
        lon += grid_size

    return tiles


def search_best_image_for_tile(token, bbox, start_date, end_date, max_cloud):
    """Find the best (least cloudy) image for a tile."""

    footprint = f"POLYGON(({bbox[0]} {bbox[1]},{bbox[2]} {bbox[1]},{bbox[2]} {bbox[3]},{bbox[0]} {bbox[3]},{bbox[0]} {bbox[1]}))"

    filter_query = (
        f"Collection/Name eq 'SENTINEL-2' and "
        f"Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value le {max_cloud}) and "
        f"ContentDate/Start gt {start_date}T00:00:00.000Z and ContentDate/Start lt {end_date}T23:59:59.999Z and "
        f"OData.CSC.Intersects(area=geography'SRID=4326;{footprint}')"
    )

    params = {
        '$filter': filter_query,
        '$orderby': 'Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq \'cloudCover\' and att/OData.CSC.DoubleAttribute/Value) asc',
        '$top': IMAGES_PER_CELL
    }

    headers = {'Authorization': f'Bearer {token}'}

    try:
        response = requests.get(SEARCH_URL, params=params, headers=headers)
        response.raise_for_status()
        results = response.json()
        return results.get('value', [])
    except Exception as e:
        print(f"    Search failed: {e}")
        return []


def download_product(token, product_id, product_name, output_dir):
    """Download a product."""

    url = f"{DOWNLOAD_URL}({product_id})/$value"
    headers = {'Authorization': f'Bearer {token}'}
    output_path = os.path.join(output_dir, f"{product_name}.zip")

    if os.path.exists(output_path):
        return True

    try:
        response = requests.get(url, headers=headers, stream=True, timeout=300)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))

        with open(output_path, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\r      Progress: {percent:.1f}%", end='')

        print(f"\n      Saved: {output_path}")
        return True

    except Exception as e:
        print(f"\n      Download failed: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return False


def main():
    print("=" * 80)
    print("Africa-Wide Sentinel-2 Downloader for CPI Detection")
    print("=" * 80)

    if USERNAME == 'your_username_here':
        print("\nERROR: Please edit the script and add your credentials!")
        return

    # Create grid
    print(f"\n1. Creating grid...")
    print(f"   Region: {AFRICA_BBOX}")
    print(f"   Grid size: {GRID_SIZE}° (~{int(GRID_SIZE * 111)}km)")

    tiles = create_grid(AFRICA_BBOX, GRID_SIZE)
    print(f"   Created {len(tiles)} tiles")

    # Estimate data size
    est_size_gb = len(tiles) * IMAGES_PER_CELL * 1.0  # ~1GB per image
    print(f"\n   ESTIMATED DOWNLOAD SIZE: ~{est_size_gb:.0f} GB")
    print(f"   ESTIMATED TIME: ~{len(tiles) * 3:.0f} minutes")

    response = input("\n   Continue? (yes/no): ")
    if response.lower() != 'yes':
        print("   Cancelled.")
        return

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Authenticate
    print("\n2. Authenticating...")
    token = get_access_token(USERNAME, PASSWORD)
    if not token:
        return
    print("   ✓ Authenticated")

    # Process each tile
    print(f"\n3. Processing {len(tiles)} tiles...")
    print("=" * 80)

    success_count = 0
    no_data_count = 0

    for i, tile_bbox in enumerate(tiles):
        print(f"\nTile {i+1}/{len(tiles)}: {tile_bbox}")

        # Search for best image
        print(f"  Searching...")
        products = search_best_image_for_tile(token, tile_bbox, START_DATE, END_DATE, MAX_CLOUD_COVER)

        if not products:
            print(f"  ✗ No images found (cloud cover > {MAX_CLOUD_COVER}% or no coverage)")
            no_data_count += 1
            continue

        # Download best image
        product = products[0]
        product_id = product['Id']
        product_name = product['Name']

        # Get cloud cover
        cloud_cover = None
        for attr in product.get('Attributes', []):
            if attr.get('Name') == 'cloudCover':
                cloud_cover = attr.get('Value')
                break

        print(f"  Found: {product_name}")
        if cloud_cover:
            print(f"  Cloud cover: {cloud_cover}%")

        print(f"  Downloading...")
        if download_product(token, product_id, product_name, OUTPUT_DIR):
            success_count += 1

        # Rate limiting (be nice to the server)
        if i < len(tiles) - 1:
            time.sleep(2)

    print("\n" + "=" * 80)
    print("Download Complete!")
    print("=" * 80)
    print(f"\nSuccessful: {success_count}/{len(tiles)} tiles")
    print(f"No data: {no_data_count}/{len(tiles)} tiles")
    print(f"Location: {OUTPUT_DIR}/")

    print("\nNext steps:")
    print("1. Unzip all files:")
    print(f"   cd {OUTPUT_DIR} && unzip '*.zip'")
    print("2. Process bands:")
    print(f"   python process_sentinel2_bands.py {OUTPUT_DIR}/")
    print("3. Run CPI detection on all images:")
    print("   python batch_detect_africa.py")

    # Save tile list for reference
    with open('tiles_processed.json', 'w') as f:
        json.dump({
            'bbox': AFRICA_BBOX,
            'grid_size': GRID_SIZE,
            'tiles': tiles,
            'success_count': success_count
        }, f, indent=2)

    print("\nTile grid saved to: tiles_processed.json")


if __name__ == '__main__':
    main()
