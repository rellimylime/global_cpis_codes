"""
Google Earth Engine script to download Sentinel-2 images for CPI detection.

This script downloads 4-band GeoTIFF images (R-G-B-NIR) from Sentinel-2.

Setup:
1. Install: pip install earthengine-api
2. Authenticate: earthengine authenticate
3. Edit the configuration below
4. Run: python download_sentinel2_gee.py
"""

import ee
import os
from datetime import datetime

# Initialize Earth Engine
try:
    ee.Initialize(project='africa-irrigation-mine')
except Exception as e:
    print(f"Error initializing Earth Engine: {e}")
    exit(1)

# ============ CONFIGURATION ============
# Edit these parameters for your area of interest

# Define your area of interest (bounding box)
# Example: Central Africa region from your ArcGIS link
# Format: [min_lon, min_lat, max_lon, max_lat]
AOI = ee.Geometry.Rectangle([10, -5, 25, 10])  # Central Africa example

# Alternative: Define AOI by country name
# AOI = ee.FeatureCollection("USDOS/LSIB_SIMPLE/2017").filter(ee.Filter.eq('country_na', 'Gabon')).geometry()

# Date range
START_DATE = '2021-06-01'
END_DATE = '2021-08-31'

# Cloud coverage threshold (0-100)
MAX_CLOUD_COVER = 20

# Output directory
OUTPUT_DIR = 'downloaded_sentinel2'

# Maximum number of images to download (set to None for all)
MAX_IMAGES = 5

# Export scale (meters per pixel)
SCALE = 10  # Sentinel-2 native resolution

# =======================================


def get_sentinel2_collection(aoi, start_date, end_date, max_cloud):
    """Get Sentinel-2 Surface Reflectance collection."""

    collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                  .filterBounds(aoi)
                  .filterDate(start_date, end_date)
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_cloud))
                  .select(['B4', 'B3', 'B2', 'B8'])  # Red, Green, Blue, NIR
                  .sort('CLOUDY_PIXEL_PERCENTAGE'))  # Least cloudy first

    return collection


def export_image_to_drive(image, aoi, description, scale=10):
    """Export image to Google Drive."""

    task = ee.batch.Export.image.toDrive(
        image=image,
        description=description,
        folder='Sentinel2_CPI_Detection',
        fileNamePrefix=description,
        region=aoi,
        scale=scale,
        crs='EPSG:4326',
        fileFormat='GeoTIFF',
        maxPixels=1e13
    )

    task.start()
    return task


def download_to_local(image, aoi, filename, scale=10):
    """Download image directly to local file (for small areas)."""

    # Get download URL
    url = image.getDownloadURL({
        'scale': scale,
        'crs': 'EPSG:4326',
        'region': aoi,
        'format': 'GEO_TIFF'
    })

    print(f"Download URL for {filename}:")
    print(url)
    print("\nCopy this URL to your browser to download the image.")
    print("-" * 80)

    return url


def main():
    print("=" * 80)
    print("Sentinel-2 Downloader for CPI Detection")
    print("=" * 80)

    # Get image collection
    print(f"\nSearching for images...")
    print(f"  Area: {AOI.getInfo()['coordinates']}")
    print(f"  Date range: {START_DATE} to {END_DATE}")
    print(f"  Max cloud cover: {MAX_CLOUD_COVER}%")

    collection = get_sentinel2_collection(AOI, START_DATE, END_DATE, MAX_CLOUD_COVER)

    # Get collection size
    count = collection.size().getInfo()
    print(f"\nFound {count} images matching criteria")

    if count == 0:
        print("\nNo images found! Try:")
        print("  - Expanding date range")
        print("  - Increasing MAX_CLOUD_COVER")
        print("  - Checking if AOI is correct")
        return

    # Limit number of images if specified
    if MAX_IMAGES:
        collection = collection.limit(MAX_IMAGES)
        print(f"Limiting to {MAX_IMAGES} images (least cloudy)")

    # Get image list
    image_list = collection.toList(collection.size())

    print("\n" + "=" * 80)
    print("OPTION 1: Export to Google Drive (Recommended for large areas)")
    print("=" * 80)

    for i in range(min(count, MAX_IMAGES or count)):
        image = ee.Image(image_list.get(i))

        # Get image metadata
        props = image.getInfo()['properties']
        image_id = props.get('PRODUCT_ID', f'image_{i}')
        gen_time = props.get('GENERATION_TIME', None)
        if gen_time:
            from datetime import datetime
            date = datetime.fromtimestamp(gen_time / 1000).strftime('%Y-%m-%d')
        else:
            date = props.get('SENSING_TIME', 'unknown_date')[:10] if isinstance(props.get('SENSING_TIME'), str) else 'unknown_date'        
        cloud_cover = props.get('CLOUDY_PIXEL_PERCENTAGE', 'unknown')
        description = f"S2_{date}_cloud{cloud_cover:.1f}_{i}"

        print(f"\nImage {i+1}:")
        print(f"  ID: {image_id}")
        print(f"  Date: {date}")
        print(f"  Cloud cover: {cloud_cover:.1f}%")

        # Export to Google Drive
        task = export_image_to_drive(image, AOI, description, SCALE)
        print(f"  Export task started: {description}")
        print(f"  Check progress at: https://code.earthengine.google.com/tasks")

    # print("\n" + "=" * 80)
    # print("OPTION 2: Direct Download URLs (For small areas < 32MB)")
    # print("=" * 80)
    # print("\nGenerating download URLs (this may take a moment)...\n")

    # urls = []
    # for i in range(min(count, MAX_IMAGES or count)):
    #     image = ee.Image(image_list.get(i))
    #     props = image.getInfo()['properties']
    #     date = props.get('GENERATION_TIME', 'unknown_date')[:10]
    #     filename = f"sentinel2_{date}_{i}.tif"

    #     try:
    #         url = download_to_local(image, AOI, filename, SCALE)
    #         urls.append((filename, url))
    #     except Exception as e:
    #         print(f"Error generating URL for {filename}: {e}")
    #         print("Area might be too large. Use Google Drive export instead.\n")

    # print("\n" + "=" * 80)
    # print("SUMMARY")
    # print("=" * 80)
    # print(f"\nImages found: {count}")
    # print(f"Images processed: {min(count, MAX_IMAGES or count)}")
    # print("\nNext steps:")
    # print("1. For Google Drive exports: Check https://code.earthengine.google.com/tasks")
    # print("2. For direct downloads: Copy the URLs above to your browser")
    # print("3. Save downloaded images to: imgs/")
    # print("4. Run: python demo.py")
    # print("\n")


if __name__ == '__main__':
    main()
