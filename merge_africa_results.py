"""
Merge all CPI detection results into one Africa-wide shapefile.

This script:
1. Finds all detection results in result_africa/
2. Merges polygons from all tiles
3. Creates a single shapefile: africa_cpis_2021.shp
4. Includes attributes: tile_id, confidence, area

Usage:
    python merge_africa_results.py
"""

import os
import sys
from glob import glob
from osgeo import ogr, osr
import json


def find_result_shapefiles(result_dir='result_africa'):
    """Find all shapefiles in result directories."""
    shapefiles = []

    if not os.path.exists(result_dir):
        print(f"ERROR: Result directory not found: {result_dir}")
        return shapefiles

    for tile_dir in os.listdir(result_dir):
        tile_path = os.path.join(result_dir, tile_dir)

        if not os.path.isdir(tile_path):
            continue

        # Look for shapefiles
        for shp_file in glob(os.path.join(tile_path, '*.shp')):
            shapefiles.append({
                'tile_name': tile_dir,
                'path': shp_file,
                'basename': os.path.basename(shp_file)
            })

    return shapefiles


def extract_tile_id(tile_name):
    """Extract numeric tile ID from tile name."""
    try:
        parts = tile_name.replace('africa_s2_2021_tile_', '').split('_')
        return int(parts[0])
    except:
        return 0


def merge_shapefiles(shapefiles, output_file='africa_cpis_2021.shp'):
    """Merge all shapefiles into one."""

    if not shapefiles:
        print("No shapefiles to merge!")
        return False

    print(f"\nMerging {len(shapefiles)} shapefiles...")

    # Create output shapefile
    driver = ogr.GetDriverByName('ESRI Shapefile')

    # Remove existing output if present
    if os.path.exists(output_file):
        driver.DeleteDataSource(output_file)

    # Create new shapefile
    out_ds = driver.CreateDataSource(output_file)

    # Use WGS84 projection
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)

    out_layer = out_ds.CreateLayer('cpis', srs, ogr.wkbPolygon)

    # Add fields
    out_layer.CreateField(ogr.FieldDefn('tile_id', ogr.OFTInteger))
    out_layer.CreateField(ogr.FieldDefn('tile_name', ogr.OFTString))

    confidence_field = ogr.FieldDefn('confidence', ogr.OFTReal)
    confidence_field.SetWidth(8)
    confidence_field.SetPrecision(2)
    out_layer.CreateField(confidence_field)

    area_field = ogr.FieldDefn('area_ha', ogr.OFTReal)
    area_field.SetWidth(12)
    area_field.SetPrecision(2)
    out_layer.CreateField(area_field)

    out_layer.CreateField(ogr.FieldDefn('class', ogr.OFTString))

    # Track statistics
    total_features = 0
    tiles_processed = 0

    # Merge each shapefile
    for i, shp_info in enumerate(shapefiles):
        tile_name = shp_info['tile_name']
        tile_id = extract_tile_id(tile_name)
        shp_path = shp_info['path']

        print(f"  Processing {i+1}/{len(shapefiles)}: {tile_name}...", end=' ')

        try:
            # Open source shapefile
            src_ds = ogr.Open(shp_path)
            if not src_ds:
                print("Failed to open")
                continue

            src_layer = src_ds.GetLayer()
            feature_count = src_layer.GetFeatureCount()

            # Copy features
            for feature in src_layer:
                geom = feature.GetGeometryRef()

                if not geom:
                    continue

                # Create new feature
                out_feature = ogr.Feature(out_layer.GetLayerDefn())

                # Copy geometry
                out_feature.SetGeometry(geom.Clone())

                # Set attributes
                out_feature.SetField('tile_id', tile_id)
                out_feature.SetField('tile_name', tile_name)

                # Try to get confidence if available
                if feature.GetFieldIndex('confidence') >= 0:
                    out_feature.SetField('confidence', feature.GetField('confidence'))
                elif feature.GetFieldIndex('score') >= 0:
                    out_feature.SetField('confidence', feature.GetField('score'))

                # Calculate area (in hectares)
                area_m2 = geom.GetArea()
                area_ha = area_m2 / 10000.0
                out_feature.SetField('area_ha', area_ha)

                # Copy class if available
                if feature.GetFieldIndex('class') >= 0:
                    out_feature.SetField('class', feature.GetField('class'))

                out_layer.CreateFeature(out_feature)
                out_feature = None

            total_features += feature_count
            tiles_processed += 1

            print(f"{feature_count} CPIs")

            src_ds = None

        except Exception as e:
            print(f"Error: {e}")

    out_ds = None

    print(f"\n✓ Merged {total_features} CPIs from {tiles_processed} tiles")
    print(f"✓ Output: {output_file}")

    return True


def create_summary_report(output_file='africa_cpis_2021.shp'):
    """Create a summary report of the merged results."""

    if not os.path.exists(output_file):
        return

    print("\n" + "=" * 80)
    print("SUMMARY REPORT")
    print("=" * 80)

    # Read shapefile
    ds = ogr.Open(output_file)
    if not ds:
        return

    layer = ds.GetLayer()
    feature_count = layer.GetFeatureCount()

    print(f"\nTotal CPIs detected: {feature_count:,}")

    # Calculate statistics
    total_area = 0
    confidence_sum = 0
    confidence_count = 0
    tiles = set()

    for feature in layer:
        area = feature.GetField('area_ha')
        if area:
            total_area += area

        confidence = feature.GetField('confidence')
        if confidence:
            confidence_sum += confidence
            confidence_count += 1

        tile_name = feature.GetField('tile_name')
        if tile_name:
            tiles.add(tile_name)

    print(f"Total area: {total_area:,.1f} hectares ({total_area/100:,.1f} km²)")
    print(f"Tiles processed: {len(tiles)}")

    if confidence_count > 0:
        avg_confidence = confidence_sum / confidence_count
        print(f"Average confidence: {avg_confidence:.2f}")

    if feature_count > 0:
        avg_area = total_area / feature_count
        print(f"Average CPI size: {avg_area:.1f} hectares")

    # Get extent
    extent = layer.GetExtent()
    print(f"\nGeographic extent:")
    print(f"  Longitude: {extent[0]:.2f}° to {extent[1]:.2f}°")
    print(f"  Latitude: {extent[2]:.2f}° to {extent[3]:.2f}°")

    ds = None

    # Save summary to JSON
    summary = {
        'total_cpis': feature_count,
        'total_area_ha': round(total_area, 1),
        'total_area_km2': round(total_area / 100, 1),
        'tiles_processed': len(tiles),
        'avg_confidence': round(avg_confidence, 2) if confidence_count > 0 else None,
        'avg_area_ha': round(avg_area, 1) if feature_count > 0 else None,
        'extent': {
            'min_lon': extent[0],
            'max_lon': extent[1],
            'min_lat': extent[2],
            'max_lat': extent[3]
        }
    }

    summary_file = 'africa_cpis_2021_summary.json'
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n✓ Summary saved to: {summary_file}")


def main():
    print("=" * 80)
    print("Merge Africa CPI Detection Results")
    print("=" * 80)

    # Find all result shapefiles
    print("\n1. Scanning for result shapefiles...")
    shapefiles = find_result_shapefiles()

    if not shapefiles:
        print("\nNo shapefiles found in result_africa/")
        print("\nMake sure you have:")
        print("  1. Run batch_detect_africa.py to process tiles")
        print("  2. Results are in result_africa/ directory")
        return

    print(f"  Found {len(shapefiles)} shapefiles")

    # Show tile coverage
    tile_names = set([s['tile_name'] for s in shapefiles])
    print(f"  Covering {len(tile_names)} tiles")

    # Merge shapefiles
    print("\n2. Merging shapefiles...")
    output_file = 'africa_cpis_2021.shp'

    if merge_shapefiles(shapefiles, output_file):
        create_summary_report(output_file)

        print("\n" + "=" * 80)
        print("SUCCESS!")
        print("=" * 80)
        print(f"\n✓ Africa-wide CPI shapefile created: {output_file}")
        print("\nYou can now:")
        print("  - Open in QGIS, ArcGIS, or other GIS software")
        print("  - Analyze CPI distribution across Africa")
        print("  - Export to other formats (GeoJSON, KML, etc.)")

        print("\n  Associated files:")
        for ext in ['.shx', '.dbf', '.prj']:
            assoc_file = output_file.replace('.shp', ext)
            if os.path.exists(assoc_file):
                print(f"    - {assoc_file}")


if __name__ == '__main__':
    main()
