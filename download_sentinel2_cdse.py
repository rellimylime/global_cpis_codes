"""
Sentinel-2 downloader using the NEW Copernicus Data Space API (2024+)

The old SciHub API and sentinelsat library no longer work.
This uses the new OAuth2-based API.

Setup:
1. Create free account at: https://dataspace.copernicus.eu/
2. Install: pip install requests oauthlib
3. Edit USERNAME and PASSWORD below
4. Run: python download_sentinel2_cdse.py
"""

import requests
import json
import os
from datetime import datetime
from urllib.parse import urlencode

# ============ CONFIGURATION ============
USERNAME = 'your_username_here'  # Your Copernicus Data Space username
PASSWORD = 'your_password_here'  # Your Copernicus Data Space password

# Area of Interest (bounding box)
# Format: [min_lon, min_lat, max_lon, max_lat]
BBOX = [16.0, 0.5, 17.0, 1.5]  # Central Africa example

# Date range
START_DATE = '2021-06-01'
END_DATE = '2021-08-31'

# Cloud coverage (0-100)
MAX_CLOUD_COVER = 20

# Max number of products to download
MAX_DOWNLOADS = 3

# Output directory
OUTPUT_DIR = 'sentinel2_products'

# =======================================

# API endpoints
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
        token = response.json()['access_token']
        return token
    except Exception as e:
        print(f"Authentication failed: {e}")
        print("\nMake sure your username and password are correct.")
        print("Create account at: https://dataspace.copernicus.eu/")
        return None


def search_products(token, bbox, start_date, end_date, max_cloud):
    """Search for Sentinel-2 products."""

    # Format dates for API
    start = f"{start_date}T00:00:00.000Z"
    end = f"{end_date}T23:59:59.999Z"

    # Build query
    footprint = f"POLYGON(({bbox[0]} {bbox[1]},{bbox[2]} {bbox[1]},{bbox[2]} {bbox[3]},{bbox[0]} {bbox[3]},{bbox[0]} {bbox[1]}))"

    filter_query = (
        f"Collection/Name eq 'SENTINEL-2' and "
        f"Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value le {max_cloud}) and "
        f"ContentDate/Start gt {start} and ContentDate/Start lt {end} and "
        f"OData.CSC.Intersects(area=geography'SRID=4326;{footprint}')"
    )

    params = {
        '$filter': filter_query,
        '$orderby': 'ContentDate/Start desc',
        '$top': 100
    }

    headers = {'Authorization': f'Bearer {token}'}

    try:
        response = requests.get(SEARCH_URL, params=params, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Search failed: {e}")
        return None


def download_product(token, product_id, product_name, output_dir):
    """Download a single product."""

    url = f"{DOWNLOAD_URL}({product_id})/$value"
    headers = {'Authorization': f'Bearer {token}'}

    output_path = os.path.join(output_dir, f"{product_name}.zip")

    if os.path.exists(output_path):
        print(f"  Already downloaded: {product_name}")
        return True

    print(f"  Downloading: {product_name}")
    print(f"    URL: {url}")

    try:
        response = requests.get(url, headers=headers, stream=True)
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
                        print(f"\r    Progress: {percent:.1f}% ({downloaded / (1024**2):.1f} MB)", end='')

        print(f"\n    Saved: {output_path}")
        return True

    except Exception as e:
        print(f"\n    Download failed: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return False


def main():
    print("=" * 80)
    print("Copernicus Data Space Sentinel-2 Downloader (2024 API)")
    print("=" * 80)

    if USERNAME == 'your_username_here':
        print("\nERROR: Please edit the script and add your credentials!")
        print("\n1. Create account at: https://dataspace.copernicus.eu/")
        print("2. Edit USERNAME and PASSWORD in this script")
        return

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Authenticate
    print("\n1. Authenticating...")
    token = get_access_token(USERNAME, PASSWORD)
    if not token:
        return
    print("   ✓ Authentication successful")

    # Search for products
    print("\n2. Searching for products...")
    print(f"   Area: {BBOX[0]}, {BBOX[1]} to {BBOX[2]}, {BBOX[3]}")
    print(f"   Dates: {START_DATE} to {END_DATE}")
    print(f"   Max cloud: {MAX_CLOUD_COVER}%")

    results = search_products(token, BBOX, START_DATE, END_DATE, MAX_CLOUD_COVER)

    if not results or 'value' not in results:
        print("   ✗ No products found!")
        print("\nTry:")
        print("  - Expanding date range")
        print("  - Increasing MAX_CLOUD_COVER")
        print("  - Checking coordinates")
        return

    products = results['value']
    print(f"   ✓ Found {len(products)} products")

    if len(products) == 0:
        return

    # Limit downloads
    products = products[:MAX_DOWNLOADS]

    # Download products
    print(f"\n3. Downloading {len(products)} product(s)...")
    print("-" * 80)

    success_count = 0
    for i, product in enumerate(products):
        print(f"\nProduct {i+1}/{len(products)}:")

        product_id = product['Id']
        product_name = product['Name']

        # Extract metadata
        cloud_cover = None
        for attr in product.get('Attributes', []):
            if attr.get('Name') == 'cloudCover':
                cloud_cover = attr.get('Value')
                break

        print(f"  Name: {product_name}")
        if cloud_cover:
            print(f"  Cloud cover: {cloud_cover}%")

        if download_product(token, product_id, product_name, OUTPUT_DIR):
            success_count += 1

    print("\n" + "=" * 80)
    print("Download Complete!")
    print("=" * 80)
    print(f"\nDownloaded: {success_count}/{len(products)} products")
    print(f"Location: {OUTPUT_DIR}/")
    print("\nNext steps:")
    print("1. Unzip the .zip files:")
    print(f"   cd {OUTPUT_DIR} && unzip '*.zip'")
    print("2. Stack bands into 4-band GeoTIFF:")
    print(f"   python process_sentinel2_bands.py {OUTPUT_DIR}/")
    print("3. Run CPI detection:")
    print("   python demo.py")


if __name__ == '__main__':
    main()
