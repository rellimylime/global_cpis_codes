import argparse
import glob
import os
import re
from datetime import datetime

from osgeo import gdal, ogr, osr


def utc_now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def threshold_text(value):
    return format(float(value), "g")


def find_mask_tifs(result_dir, thr_text):
    mask_files = []
    pattern = f"*union_segm_{thr_text}.tif"
    for tile_dir in sorted(os.listdir(result_dir)):
        tile_path = os.path.join(result_dir, tile_dir)
        if not os.path.isdir(tile_path):
            continue
        hits = glob.glob(os.path.join(tile_path, pattern))
        for p in hits:
            mask_files.append((tile_dir, p))
    return mask_files


def make_output_layer(output_shp, srs):
    driver = ogr.GetDriverByName("ESRI Shapefile")
    if os.path.exists(output_shp):
        driver.DeleteDataSource(output_shp)
    out_ds = driver.CreateDataSource(output_shp)
    if out_ds is None:
        raise RuntimeError(f"Could not create output shapefile: {output_shp}")

    layer_name = os.path.splitext(os.path.basename(output_shp))[0]
    out_lyr = out_ds.CreateLayer(layer_name, srs=srs, geom_type=ogr.wkbPolygon)
    if out_lyr is None:
        raise RuntimeError(f"Could not create output layer: {layer_name}")

    out_lyr.CreateField(ogr.FieldDefn("tile_name", ogr.OFTString))
    out_lyr.CreateField(ogr.FieldDefn("thr", ogr.OFTReal))
    out_lyr.CreateField(ogr.FieldDefn("src_file", ogr.OFTString))
    out_lyr.CreateField(ogr.FieldDefn("px_val", ogr.OFTInteger))
    return out_ds, out_lyr


def extract_tile_id(tile_name):
    m = re.search(r"tile_(\d+)", tile_name)
    if not m:
        return -1
    try:
        return int(m.group(1))
    except Exception:
        return -1


def polygonize_one(mask_path, tile_name, tile_id, thr, out_lyr, verbose):
    ds = gdal.Open(mask_path)
    if ds is None:
        raise RuntimeError(f"Could not open mask: {mask_path}")
    band = ds.GetRasterBand(1)
    if band is None:
        raise RuntimeError(f"No band found in mask: {mask_path}")

    # Build temporary in-memory layer for polygonization output.
    mem_driver = ogr.GetDriverByName("Memory")
    mem_ds = mem_driver.CreateDataSource("")
    mem_lyr = mem_ds.CreateLayer("poly", srs=out_lyr.GetSpatialRef(), geom_type=ogr.wkbPolygon)
    mem_lyr.CreateField(ogr.FieldDefn("DN", ogr.OFTInteger))
    dn_idx = mem_lyr.GetLayerDefn().GetFieldIndex("DN")

    # Use the mask band itself as validity mask to emit only non-zero regions.
    # This avoids generating huge background polygons.
    gdal.Polygonize(band, band, mem_lyr, dn_idx, [], callback=None)

    copied = 0
    for feat in mem_lyr:
        geom = feat.GetGeometryRef()
        if geom is None:
            continue
        dn = feat.GetField("DN")
        if dn is None or int(dn) <= 0:
            continue

        out_feat = ogr.Feature(out_lyr.GetLayerDefn())
        out_feat.SetGeometry(geom.Clone())
        out_feat.SetField("tile_name", tile_name[:254])
        out_feat.SetField("tile_id", int(tile_id))
        out_feat.SetField("thr", float(thr))
        out_feat.SetField("src_file", os.path.basename(mask_path)[:254])
        out_feat.SetField("px_val", int(dn))
        out_lyr.CreateFeature(out_feat)
        out_feat = None
        copied += 1

    mem_ds = None
    ds = None
    if verbose:
        print(f"[{utc_now()}Z] {tile_name}: polygons={copied}")
    return copied


def main():
    parser = argparse.ArgumentParser(
        description="Merge union_segm mask TIFFs into a single shapefile"
    )
    parser.add_argument(
        "--result-dir",
        default="result_africa",
        help="Result directory containing per-tile folders with union_segm_*.tif files",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.3,
        help="Threshold suffix to merge (e.g., 0.3 or 0.85)",
    )
    parser.add_argument(
        "--output-shp",
        default="africa_cpis_2021_thr03.shp",
        help="Output shapefile path",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-tile polygon counts",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.result_dir):
        raise SystemExit(f"Result directory not found: {args.result_dir}")

    thr_text = threshold_text(args.threshold)
    files = find_mask_tifs(args.result_dir, thr_text)
    if not files:
        raise SystemExit(
            f"No mask files found for threshold {thr_text} under {args.result_dir}. "
            f"Expected files like *union_segm_{thr_text}.tif"
        )

    # Use SRS from first raster.
    sample = gdal.Open(files[0][1])
    proj = sample.GetProjection()
    sample = None
    srs = osr.SpatialReference()
    if proj:
        srs.ImportFromWkt(proj)
    else:
        srs.ImportFromEPSG(4326)

    out_ds, out_lyr = make_output_layer(args.output_shp, srs)
    out_lyr.CreateField(ogr.FieldDefn("tile_id", ogr.OFTInteger))

    print(f"[{utc_now()}Z] Found {len(files)} mask files for threshold {thr_text}")
    total_polys = 0
    for tile_name, mask_path in files:
        tile_id = extract_tile_id(tile_name)
        count = polygonize_one(mask_path, tile_name, tile_id, args.threshold, out_lyr, args.verbose)
        total_polys += count

    out_ds = None
    print(f"[{utc_now()}Z] Wrote {total_polys} polygons to {args.output_shp}")


if __name__ == "__main__":
    main()
