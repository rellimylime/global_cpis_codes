import os
import sys
import argparse
import warnings
import re
import json
import time
from datetime import datetime
from collections import defaultdict

import numpy as np
try:
    from osgeo import gdal
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing dependency 'osgeo' (GDAL). Run this script with the CPI environment "
        "interpreter, for example: "
        "\"C:\\Users\\ermil\\.conda\\envs\\cpi_detect\\python.exe batch_detect_africa.py ...\""
    ) from exc

try:
    import geopandas as gpd
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency 'geopandas'. Activate/install the CPI detection environment first.") from exc

try:
    from shapely.geometry import box
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency 'shapely'. Activate/install the CPI detection environment first.") from exc

from tools.detect_scripts import detect_sentinel_batch

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

warnings.filterwarnings('ignore', category=UserWarning)
warnings.filterwarnings('ignore', category=FutureWarning)

gdal.UseExceptions()


def utc_now_iso():
    return datetime.utcnow().isoformat() + 'Z'


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def load_json(path, default_value):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return default_value


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def build_logger(log_file=None):
    if log_file:
        ensure_dir(os.path.dirname(log_file) or '.')

    def _log(message):
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        line = f"[{timestamp}Z] {message}"
        print(line, flush=True)
        if log_file:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(line + '\n')

    return _log


def threshold_suffix(value):
    # Matches how f"{st}" renders for simple decimal floats (0.3, 0.85, etc.)
    return format(float(value), 'g')


def _resolve_shp_path(path):
    if os.path.isfile(path) and path.lower().endswith('.shp'):
        return path
    if os.path.isdir(path):
        shp_files = sorted(
            os.path.join(path, fn)
            for fn in os.listdir(path)
            if fn.lower().endswith('.shp')
        )
        if shp_files:
            return shp_files[0]
    return None


def resolve_arid_shapefile() -> str:
    """Find the arid-region shapefile path across branch variants."""
    candidates = [
        'Africa_Arid_Regions_All-shp',
        'SSA_All_Arid_by_Country-shp',
        os.path.join('Africa_Arid_Regions_All-shp', 'Africa_Arid_Regions_All-shp.shp'),
        os.path.join('SSA_All_Arid_by_Country-shp', 'SSA_All_Arid_by_Country-shp.shp'),
    ]
    for path in candidates:
        shp_path = _resolve_shp_path(path)
        if shp_path is not None:
            return shp_path
    return None


def ensure_progress_schema(progress):
    progress.setdefault('completed_tiles', [])
    progress.setdefault('failed_tiles', [])
    progress.setdefault('no_detection_tiles', [])
    progress.setdefault('total_completed', len(progress.get('completed_tiles', [])))
    progress.setdefault('processing_history', [])
    progress.setdefault('last_updated', None)
    return progress


def load_processing_progress(progress_file):
    progress = load_json(progress_file, {
        'completed_tiles': [],
        'failed_tiles': [],
        'no_detection_tiles': [],
        'total_completed': 0,
        'processing_history': [],
        'last_updated': None,
    })
    return ensure_progress_schema(progress)


def save_processing_progress(progress_file, progress):
    progress['total_completed'] = len(set(progress.get('completed_tiles', [])))
    progress['last_updated'] = utc_now_iso()
    save_json(progress_file, progress)


def ensure_manifest_schema(manifest):
    manifest.setdefault('version', 1)
    manifest.setdefault('entries', {})
    manifest.setdefault('updated', None)
    return manifest


def load_manifest(path):
    manifest = load_json(path, {'version': 1, 'entries': {}, 'updated': None})
    return ensure_manifest_schema(manifest)


def save_manifest(path, manifest):
    manifest['updated'] = utc_now_iso()
    save_json(path, manifest)


def file_signature(path):
    st = os.stat(path)
    return {'size': int(st.st_size), 'mtime_ns': int(st.st_mtime_ns)}


def entry_signature_matches(entry, signature):
    return entry.get('sig') == signature


def preprocess_manifest_key(input_path, args):
    return (
        f"pre|{os.path.abspath(input_path)}|mode={args.preprocess_mode}|"
        f"p_low={args.p_low}|p_high={args.p_high}|max_samples={args.percentile_max_samples}|"
        f"fixed_min={args.fixed_scale_min}|fixed_max={args.fixed_scale_max}"
    )


def chip_manifest_key(preprocessed_path, args):
    sig = file_signature(preprocessed_path)
    return (
        f"chip|{os.path.abspath(preprocessed_path)}|size={sig['size']}|mtime={sig['mtime_ns']}|"
        f"chip_size={args.chip_size}|chip_overlap={args.chip_overlap}"
    )


def validate_preprocessed_tif(path):
    ds = gdal.Open(path)
    if ds is None:
        raise RuntimeError(f"Could not open preprocessed file: {path}")

    if ds.RasterCount < 4:
        raise RuntimeError(f"Preprocessed file has {ds.RasterCount} bands (<4): {path}")

    for i in range(1, 5):
        band = ds.GetRasterBand(i)
        dtype = gdal.GetDataTypeName(band.DataType)
        if dtype != 'Byte':
            raise RuntimeError(f"Preprocessed file band {i} dtype is {dtype}, expected Byte: {path}")


def compute_p1p99_scale_params(dataset, p_low, p_high, max_samples):
    width = dataset.RasterXSize
    height = dataset.RasterYSize
    total_pixels = max(1, width * height)

    downsample = max(1, int((total_pixels / float(max_samples)) ** 0.5))
    sample_width = max(128, int(width / downsample))
    sample_height = max(128, int(height / downsample))

    scale_params = []
    for i in range(1, 5):
        band = dataset.GetRasterBand(i)
        arr = band.ReadAsArray(buf_xsize=sample_width, buf_ysize=sample_height)
        arr = np.asarray(arr, dtype=np.float32)
        arr = arr[np.isfinite(arr)]

        if arr.size == 0:
            raise RuntimeError(f"No finite pixels available for percentile scaling (band {i})")

        lo = float(np.percentile(arr, p_low))
        hi = float(np.percentile(arr, p_high))
        if hi <= lo:
            hi = lo + 1.0

        scale_params.append((lo, hi, 0.0, 255.0))

    return scale_params


def preprocess_image(input_path, args, manifest):
    if args.preprocess_mode == 'none':
        return input_path, {'cached': True, 'mode': 'none'}

    key = preprocess_manifest_key(input_path, args)
    sig = file_signature(input_path)

    cached_entry = manifest['entries'].get(key)
    if cached_entry and cached_entry.get('status') == 'ok':
        if entry_signature_matches(cached_entry, sig):
            out_path = cached_entry.get('output_path')
            if out_path and os.path.exists(out_path):
                return out_path, {
                    'cached': True,
                    'mode': args.preprocess_mode,
                    'scale_params': cached_entry.get('scale_params', []),
                }

    ensure_dir(args.preprocess_cache_dir)

    ds = gdal.Open(input_path)
    if ds is None:
        raise RuntimeError(f"Could not open input raster: {input_path}")

    if ds.RasterCount < 4:
        raise RuntimeError(f"Input raster has {ds.RasterCount} bands (<4): {input_path}")

    base = os.path.splitext(os.path.basename(input_path))[0]
    if args.preprocess_mode == 'fixed':
        fixed_min = float(args.fixed_scale_min)
        fixed_max = float(args.fixed_scale_max)
        if abs(fixed_min - 0.0) < 1e-9 and abs(fixed_max - 12520.0) < 1e-9:
            out_name = f"{base}_rgbnir_u8.tif"
        else:
            min_tag = format(fixed_min, 'g').replace('.', 'p')
            max_tag = format(fixed_max, 'g').replace('.', 'p')
            out_name = f"{base}_rgbnir_u8_fx{min_tag}_{max_tag}.tif"
        scale_params = [(fixed_min, fixed_max, 0.0, 255.0)] * 4
    else:
        p_low_tag = str(args.p_low).replace('.', 'p')
        p_high_tag = str(args.p_high).replace('.', 'p')
        out_name = f"{base}_rgbnir_u8_p{p_low_tag}_p{p_high_tag}.tif"
        scale_params = compute_p1p99_scale_params(
            dataset=ds,
            p_low=args.p_low,
            p_high=args.p_high,
            max_samples=args.percentile_max_samples,
        )

    out_path = os.path.join(args.preprocess_cache_dir, out_name)

    options = gdal.TranslateOptions(
        format='GTiff',
        bandList=[1, 2, 3, 4],
        outputType=gdal.GDT_Byte,
        scaleParams=scale_params,
        creationOptions=['COMPRESS=LZW', 'TILED=YES', 'BIGTIFF=IF_SAFER'],
    )

    result = gdal.Translate(out_path, ds, options=options)
    ds = None
    if result is None:
        raise RuntimeError(f"gdal.Translate failed for {input_path}")
    result = None

    validate_preprocessed_tif(out_path)

    manifest['entries'][key] = {
        'status': 'ok',
        'updated': utc_now_iso(),
        'input_path': os.path.abspath(input_path),
        'sig': sig,
        'output_path': os.path.abspath(out_path),
        'mode': args.preprocess_mode,
        'scale_params': scale_params,
    }

    return out_path, {
        'cached': False,
        'mode': args.preprocess_mode,
        'scale_params': scale_params,
    }


def chip_positions(total_size, chip_size, overlap):
    stride = max(1, chip_size - overlap)
    if total_size <= chip_size:
        return [0]

    positions = list(range(0, total_size - chip_size + 1, stride))
    if positions[-1] != total_size - chip_size:
        positions.append(total_size - chip_size)
    return positions


def split_image_into_chips(preprocessed_path, args, manifest):
    ensure_dir(args.chip_cache_dir)

    key = chip_manifest_key(preprocessed_path, args)
    cached_entry = manifest['entries'].get(key)
    if cached_entry and cached_entry.get('status') == 'ok':
        chips = cached_entry.get('chips', [])
        if chips and all(os.path.exists(os.path.join(args.chip_cache_dir, c['name'])) for c in chips):
            return chips, {'cached': True}

    ds = gdal.Open(preprocessed_path)
    if ds is None:
        raise RuntimeError(f"Could not open preprocessed raster for chipping: {preprocessed_path}")

    width = ds.RasterXSize
    height = ds.RasterYSize

    x_positions = chip_positions(width, args.chip_size, args.chip_overlap)
    y_positions = chip_positions(height, args.chip_size, args.chip_overlap)

    base = os.path.splitext(os.path.basename(preprocessed_path))[0]
    chips = []

    for y in y_positions:
        for x in x_positions:
            w = min(args.chip_size, width - x)
            h = min(args.chip_size, height - y)

            chip_name = f"{base}__x{x:05d}_y{y:05d}.tif"
            chip_path = os.path.join(args.chip_cache_dir, chip_name)

            if not os.path.exists(chip_path):
                options = gdal.TranslateOptions(
                    format='GTiff',
                    srcWin=[x, y, w, h],
                    creationOptions=['COMPRESS=LZW', 'TILED=YES', 'BIGTIFF=IF_SAFER'],
                )
                result = gdal.Translate(chip_path, ds, options=options)
                if result is None:
                    raise RuntimeError(f"Failed to create chip {chip_name}")
                result = None

            chips.append({
                'name': chip_name,
                'x': int(x),
                'y': int(y),
                'w': int(w),
                'h': int(h),
            })

    ds = None

    manifest['entries'][key] = {
        'status': 'ok',
        'updated': utc_now_iso(),
        'preprocessed_path': os.path.abspath(preprocessed_path),
        'chips': chips,
        'chip_size': int(args.chip_size),
        'chip_overlap': int(args.chip_overlap),
    }

    return chips, {'cached': False}


def write_mask_with_reference(mask_array, reference_path, out_path):
    ref_ds = gdal.Open(reference_path)
    if ref_ds is None:
        raise RuntimeError(f"Could not open reference raster for output georeference: {reference_path}")

    height, width = mask_array.shape
    driver = gdal.GetDriverByName('GTiff')
    out_ds = driver.Create(
        out_path,
        width,
        height,
        1,
        gdal.GDT_Byte,
        options=['COMPRESS=LZW', 'TILED=YES', 'BIGTIFF=IF_SAFER'],
    )
    if out_ds is None:
        raise RuntimeError(f"Failed to create output raster: {out_path}")

    out_ds.SetGeoTransform(ref_ds.GetGeoTransform())
    out_ds.SetProjection(ref_ds.GetProjection())

    out_band = out_ds.GetRasterBand(1)
    out_band.WriteArray(mask_array)
    out_band.SetNoDataValue(0)

    out_ds.FlushCache()
    out_ds = None
    ref_ds = None


def merge_chip_results_for_source(record, score_thresholds, seg_res_path):
    output_name = record['output_name']
    preprocessed_path = record['preprocessed_path']
    chips = record['chips']

    ref_ds = gdal.Open(preprocessed_path)
    if ref_ds is None:
        raise RuntimeError(f"Cannot open reference raster for merge: {preprocessed_path}")

    width = ref_ds.RasterXSize
    height = ref_ds.RasterYSize
    ref_ds = None

    output_dir = os.path.join(seg_res_path, output_name)
    ensure_dir(output_dir)

    merged_thresholds = []
    for thr in score_thresholds:
        thr_text = threshold_suffix(thr)
        merged = np.zeros((height, width), dtype=np.uint8)
        used_chip_count = 0

        for chip in chips:
            chip_base = os.path.splitext(chip['name'])[0]
            chip_mask_path = os.path.join(
                seg_res_path,
                chip_base,
                f"{chip_base}union_segm_{thr_text}.tif",
            )
            if not os.path.exists(chip_mask_path):
                continue

            chip_ds = gdal.Open(chip_mask_path)
            if chip_ds is None:
                continue
            chip_mask = chip_ds.ReadAsArray()
            chip_ds = None
            if chip_mask is None:
                continue
            if chip_mask.ndim > 2:
                chip_mask = chip_mask[0]

            y = int(chip['y'])
            x = int(chip['x'])
            h, w = chip_mask.shape
            target = merged[y:y + h, x:x + w]
            np.maximum(target, chip_mask.astype(np.uint8), out=target)
            used_chip_count += 1

        if used_chip_count > 0:
            out_path = os.path.join(output_dir, f"{output_name}union_segm_{thr_text}.tif")
            write_mask_with_reference(merged, preprocessed_path, out_path)
            merged_thresholds.append(thr_text)

    return merged_thresholds


def extract_tile_bbox(filename):
    """Extract bounding box from tile filename or metadata."""
    match = re.search(r'tile_(\d+)', filename)
    if not match:
        return None

    tile_id = int(match.group(1))

    metadata_files = [
        'africa_tiles_2021_metadata.json',
        'africa_tiles_2021_batch_1.json',
        'gee_export_progress.json',
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


def is_derived_tif(filename):
    lower = filename.lower()
    return ('_rgbnir_u8' in lower) or ('__x' in lower)


def filter_arid_tiles(img_list, shapefile_path=None):
    """Filter image list to only those in arid regions."""
    print("\nFiltering tiles to arid regions only...")

    if shapefile_path is None:
        shapefile_path = resolve_arid_shapefile()
    else:
        shapefile_path = _resolve_shp_path(shapefile_path)

    if shapefile_path is None or not os.path.exists(shapefile_path):
        raise RuntimeError('Arid shapefile not found. Use --skip-arid-filter to bypass this check.')

    print(f"  Using arid shapefile: {shapefile_path}")
    arid_gdf = gpd.read_file(shapefile_path)
    if arid_gdf.crs != 'EPSG:4326':
        arid_gdf = arid_gdf.to_crs('EPSG:4326')

    arid_union = arid_gdf.union_all() if hasattr(arid_gdf, 'union_all') else arid_gdf.unary_union

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


def remove_chip_result_dirs(seg_res_path, chip_names):
    for chip_name in chip_names:
        chip_base = os.path.splitext(chip_name)[0]
        chip_dir = os.path.join(seg_res_path, chip_base)
        if os.path.isdir(chip_dir):
            # Best-effort cleanup to save disk.
            try:
                for root, dirs, files in os.walk(chip_dir, topdown=False):
                    for fn in files:
                        os.remove(os.path.join(root, fn))
                    for dn in dirs:
                        os.rmdir(os.path.join(root, dn))
                os.rmdir(chip_dir)
            except Exception:
                pass


def summarize_and_exit(has_failures, allow_partial):
    if has_failures and not allow_partial:
        print('\nOne or more files failed. Exiting with code 1 to avoid silent errors.')
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Batch CPI detection with cached preprocessing and optional chip mode')

    parser.add_argument('--auto', action='store_true', help='Run without interactive confirmation prompt')
    parser.add_argument('--img_dir', type=str, default='imgs', help='Directory containing input GeoTIFF files')
    parser.add_argument('--batch-size', type=int, default=50, help='Maximum source files to process per run')
    parser.add_argument('--skip-arid-filter', action='store_true', help='Skip arid shapefile filtering')
    parser.add_argument('--include-derived', action='store_true',
                        help='Also include derived TIFFs (e.g., _rgbnir_u8, chip TIFFs) from --img_dir')

    parser.add_argument(
        '--score-thr',
        nargs='+',
        type=float,
        default=[0.3, 0.85],
        help='One or more score thresholds for output masks (original default: 0.3 0.85)',
    )

    parser.add_argument('--infer-score-thr', type=float, default=None, help='Model inference score threshold override')
    parser.add_argument('--infer-nms-iou', type=float, default=None, help='Model inference NMS IoU threshold override')
    parser.add_argument('--infer-max-per-img', type=int, default=None, help='Max detections per image at inference override')
    parser.add_argument('--infer-mask-thr', type=float, default=None, help='Mask binarization threshold override')

    parser.add_argument('--preprocess-mode', choices=['none', 'fixed', 'p1p99'], default='fixed',
                        help='Preprocess mode: none (raw), fixed (0..12520), p1p99 (adaptive percentile stretch)')
    parser.add_argument('--preprocess-cache-dir', type=str, default='imgs_cache_preprocessed',
                        help='Directory for cached preprocessed rasters')
    parser.add_argument('--preprocess-manifest', type=str, default='preprocess_manifest.json',
                        help='Manifest JSON for preprocessing/chip cache metadata')
    parser.add_argument('--p-low', type=float, default=1.0, help='Lower percentile for p1p99 mode')
    parser.add_argument('--p-high', type=float, default=99.0, help='Upper percentile for p1p99 mode')
    parser.add_argument('--percentile-max-samples', type=int, default=2000000,
                        help='Approx max sample pixels per band for percentile estimation')
    parser.add_argument('--fixed-scale-min', type=float, default=0.0,
                        help='Lower raw value for fixed scaling mode')
    parser.add_argument('--fixed-scale-max', type=float, default=12520.0,
                        help='Upper raw value for fixed scaling mode')

    parser.add_argument('--chip-size', type=int, default=0,
                        help='Chip size in pixels. 0 disables chip mode (process full raster).')
    parser.add_argument('--chip-overlap', type=int, default=128,
                        help='Chip overlap in pixels when --chip-size > 0')
    parser.add_argument('--chip-cache-dir', type=str, default='imgs_cache_chips',
                        help='Directory for cached chips')
    parser.add_argument('--no-merge-chip-results', action='store_true',
                        help='Do not merge chip-level results back to source-level masks')
    parser.add_argument('--cleanup-chip-results', action='store_true',
                        help='Delete per-chip result folders after merge to save disk')

    parser.add_argument('--preprocess-only', action='store_true',
                        help='Run preprocessing/chipping only and exit before detection')
    parser.add_argument('--allow-partial', action='store_true',
                        help='Exit code 0 even if some files fail')
    parser.add_argument('--ignore-progress', action='store_true',
                        help='Ignore progress file and process files even if already completed')

    parser.add_argument('--progress-file', type=str, default='africa_detection_progress.json',
                        help='Progress tracking JSON file')
    parser.add_argument('--seg-res-path', type=str, default='result_africa',
                        help='Output directory for segmentation masks')
    parser.add_argument('--workdir', type=str, default='temp',
                        help='Temporary working directory for detection internals')
    parser.add_argument('--log-file', type=str, default='',
                        help='Optional text log file for timestamped progress lines')
    parser.add_argument('--quiet-progress', action='store_true',
                        help='Reduce per-file progress logging')

    args = parser.parse_args()

    if args.p_low >= args.p_high:
        raise ValueError('--p-low must be smaller than --p-high')
    if args.fixed_scale_min >= args.fixed_scale_max:
        raise ValueError('--fixed-scale-min must be smaller than --fixed-scale-max')

    if args.chip_size < 0:
        raise ValueError('--chip-size must be >= 0')
    if args.chip_overlap < 0:
        raise ValueError('--chip-overlap must be >= 0')
    if args.chip_size > 0 and args.chip_overlap >= args.chip_size:
        raise ValueError('--chip-overlap must be smaller than --chip-size')

    score_thresholds = sorted(set(float(s) for s in args.score_thr))
    batch_size = max(1, int(args.batch_size))
    merge_chip_results = not args.no_merge_chip_results
    verbose_progress = not args.quiet_progress

    ensure_dir(args.seg_res_path)
    ensure_dir('run_reports')
    if args.preprocess_mode != 'none':
        ensure_dir(args.preprocess_cache_dir)
    if args.chip_size > 0:
        ensure_dir(args.chip_cache_dir)

    run_id = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    log_file = args.log_file.strip() if args.log_file else os.path.join('run_reports', f'progress_{run_id}.log')
    log = build_logger(log_file)
    run_started_at = time.time()

    log('=' * 80)
    log('Batch CPI Detection for Africa (Robust Mode)')
    log('=' * 80)
    log(f"Command config: img_dir={args.img_dir}, batch_size={batch_size}, preprocess_mode={args.preprocess_mode}, "
        f"chip_size={args.chip_size}, score_thr={score_thresholds}")
    if args.preprocess_mode == 'fixed':
        log(f"Fixed scaling range: [{args.fixed_scale_min}, {args.fixed_scale_max}]")
    if args.preprocess_mode == 'p1p99':
        log(f"Percentile scaling: p_low={args.p_low}, p_high={args.p_high}")
    log(f"Progress file: {args.progress_file}")
    log(f"Manifest file: {args.preprocess_manifest}")
    log(f"Progress log: {log_file}")

    progress = load_processing_progress(args.progress_file)
    completed = set(progress['completed_tiles'])

    if completed and not args.ignore_progress:
        log(f"Found {len(completed)} previously completed source files")

    model_cfg = dict(
        cfg_file='model/cascade_mask_rcnn_pointrend_cbam.py',
        checkpoint='model/cascade_mask_rcnn_pointrend_cbam.pth',
        infer_score_thr=args.infer_score_thr,
        infer_nms_iou=args.infer_nms_iou,
        infer_max_per_img=args.infer_max_per_img,
        infer_mask_thr_binary=args.infer_mask_thr,
    )

    preprocess_cfg = dict(
        ref_dataset_json='model/ann.json',
    )

    result_merge_cfg = dict(
        nms_thr=0.1,
        nms_merge_cats=True,
        score_thr=score_thresholds,
    )

    if not os.path.exists(args.img_dir):
        log(f"ERROR: Directory not found: {args.img_dir}")
        sys.exit(1)

    all_img_files = [
        os.path.join(args.img_dir, f)
        for f in os.listdir(args.img_dir)
        if f.lower().endswith('.tif')
    ]

    if not args.include_derived:
        raw_count = len(all_img_files)
        all_img_files = [
            path for path in all_img_files
            if not is_derived_tif(os.path.basename(path))
        ]
        skipped_derived = raw_count - len(all_img_files)
        if skipped_derived > 0:
            log(f"Excluded {skipped_derived} derived TIFF files from source scan")

    if len(all_img_files) == 0:
        log(f"ERROR: No .tif files found in {args.img_dir}/")
        sys.exit(1)

    if args.skip_arid_filter:
        img_list = all_img_files
        log(f"Skipping arid filter: {len(img_list)} candidate files")
    else:
        img_list = filter_arid_tiles(all_img_files)
        log(f"Arid filter retained {len(img_list)} candidate files")

    if not args.ignore_progress:
        img_list = [img for img in img_list if os.path.basename(img) not in completed]

    if len(img_list) == 0:
        log('All tiles already processed.')
        return

    img_list = sorted(img_list)
    total_remaining = len(img_list)
    source_batch = img_list[:batch_size]

    log('=' * 80)
    log('PROCESSING STATUS')
    log('=' * 80)
    log(f"Remaining candidate files: {total_remaining}")
    log(f"This source batch: {len(source_batch)}")
    log(f"Preprocess mode: {args.preprocess_mode}")
    log(f"Chip mode: {'on' if args.chip_size > 0 else 'off'}")
    if args.chip_size > 0:
        log(f"Chip size/overlap: {args.chip_size}/{args.chip_overlap}")

    if not args.auto:
        response = input('\nContinue? (yes/no): ')
        if response.lower() != 'yes':
            log('Cancelled by user.')
            return

    manifest = load_manifest(args.preprocess_manifest)

    preprocess_failures = {}
    preprocess_records = []

    preprocess_started_at = time.time()
    log('=' * 80)
    log('Preprocessing source files...')
    log('=' * 80)

    for idx, raw_path in enumerate(source_batch, 1):
        raw_name = os.path.basename(raw_path)
        tile_started_at = time.time()
        if verbose_progress:
            log(f"[preprocess {idx}/{len(source_batch)}] {raw_name}")
        try:
            preprocessed_path, info = preprocess_image(raw_path, args, manifest)
            record = {
                'raw_name': raw_name,
                'raw_path': raw_path,
                'preprocessed_path': preprocessed_path,
                'preprocessed_name': os.path.basename(preprocessed_path),
                'output_name': os.path.splitext(os.path.basename(preprocessed_path))[0],
                'chips': [],
                'preprocess_cached': bool(info.get('cached', False)),
            }

            if args.chip_size > 0:
                chips, chip_info = split_image_into_chips(preprocessed_path, args, manifest)
                record['chips'] = chips
                record['chip_cached'] = bool(chip_info.get('cached', False))
                if verbose_progress:
                    elapsed = time.time() - tile_started_at
                    log(f"  chips: {len(chips)} ({'cache hit' if record['chip_cached'] else 'generated'}), "
                        f"elapsed={elapsed:.1f}s")
            else:
                if verbose_progress:
                    elapsed = time.time() - tile_started_at
                    log(f"  preprocess: {'cache hit' if record['preprocess_cached'] else 'generated'}, "
                        f"elapsed={elapsed:.1f}s")

            preprocess_records.append(record)

        except Exception as e:
            preprocess_failures[raw_name] = str(e)
            log(f"  PREPROCESS FAILED: {e}")

    save_manifest(args.preprocess_manifest, manifest)
    log(f"Preprocess manifest updated: {args.preprocess_manifest}")
    log(f"Preprocess stage elapsed: {time.time() - preprocess_started_at:.1f}s")

    if preprocess_failures:
        log(f"Preprocess failures: {len(preprocess_failures)}")

    if not preprocess_records:
        log('No files available for detection after preprocessing.')
        summarize_and_exit(has_failures=True, allow_partial=args.allow_partial)
        return

    if args.preprocess_only:
        log('Preprocess-only run complete.')
        summarize_and_exit(has_failures=bool(preprocess_failures), allow_partial=args.allow_partial)
        return

    log('=' * 80)
    log('Starting detection...')
    log('=' * 80)

    detect_names = []
    detect_to_raw = {}
    raw_to_chip_names = defaultdict(list)

    if args.chip_size > 0:
        detect_img_dir = args.chip_cache_dir
        for record in preprocess_records:
            raw_name = record['raw_name']
            for chip in record['chips']:
                chip_name = chip['name']
                detect_names.append(chip_name)
                detect_to_raw[chip_name] = raw_name
                raw_to_chip_names[raw_name].append(chip_name)
    else:
        detect_img_dir = args.img_dir if args.preprocess_mode == 'none' else args.preprocess_cache_dir
        for record in preprocess_records:
            detect_name = record['raw_name'] if args.preprocess_mode == 'none' else record['preprocessed_name']
            record['detect_name'] = detect_name
            detect_names.append(detect_name)
            detect_to_raw[detect_name] = record['raw_name']

    detect_started_at = time.time()
    log(f"Detection inputs prepared: {len(detect_names)} items from directory {detect_img_dir}")
    detect_summary = detect_sentinel_batch(
        ori_img_dir=detect_img_dir,
        img_list_file=detect_names,
        workdir=args.workdir,
        seg_res_path=args.seg_res_path,
        model_cfg=model_cfg,
        **preprocess_cfg,
        **result_merge_cfg,
    )
    log(f"Detection stage elapsed: {time.time() - detect_started_at:.1f}s")

    detect_processed = set(detect_summary.get('processed', []))
    detect_failed = set(detect_summary.get('failed', []))
    detect_no_detection = set(detect_summary.get('no_detection', []))
    log(f"Detection summary: processed={len(detect_processed)}, failed={len(detect_failed)}, "
        f"no_detection={len(detect_no_detection)}")

    attempted = set(detect_names)
    missing = attempted - detect_processed - detect_failed - detect_no_detection
    if missing:
        log(f"WARNING: {len(missing)} files were attempted but not reported as success/failure/no-detection.")
        for name in sorted(missing):
            log(f"  Missing status: {name}")
        detect_failed |= missing

    raw_failed = set(preprocess_failures.keys())
    raw_completed = set()
    raw_no_detection = set()

    merged_outputs = {}

    if args.chip_size > 0:
        record_by_raw = {r['raw_name']: r for r in preprocess_records}

        for raw_name, chip_names in raw_to_chip_names.items():
            chip_set = set(chip_names)
            failed_chip_count = len(chip_set & detect_failed)
            if failed_chip_count > 0:
                raw_failed.add(raw_name)
                continue

            raw_completed.add(raw_name)
            if chip_set and chip_set.issubset(detect_no_detection):
                raw_no_detection.add(raw_name)

            if merge_chip_results:
                record = record_by_raw[raw_name]
                try:
                    merged_thresholds = merge_chip_results_for_source(
                        record=record,
                        score_thresholds=score_thresholds,
                        seg_res_path=args.seg_res_path,
                    )
                    merged_outputs[raw_name] = merged_thresholds
                except Exception as e:
                    log(f"MERGE FAILED for {raw_name}: {e}")
                    raw_failed.add(raw_name)
                    if raw_name in raw_completed:
                        raw_completed.remove(raw_name)
            if verbose_progress and raw_name in raw_completed:
                status = 'no_detection' if raw_name in raw_no_detection else 'detected'
                log(f"  source status: {raw_name} -> {status}")

        if args.cleanup_chip_results:
            remove_chip_result_dirs(args.seg_res_path, detect_names)
            log(f"Removed {len(detect_names)} chip result directories after merge")

    else:
        for record in preprocess_records:
            raw_name = record['raw_name']
            detect_name = record['detect_name']

            if detect_name in detect_failed:
                raw_failed.add(raw_name)
                continue

            raw_completed.add(raw_name)
            if detect_name in detect_no_detection:
                raw_no_detection.add(raw_name)
            if verbose_progress:
                status = 'no_detection' if detect_name in detect_no_detection else 'detected'
                log(f"  source status: {raw_name} -> {status}")

    completed_set = set(progress['completed_tiles']) | raw_completed
    failed_set = set(progress['failed_tiles']) | raw_failed
    no_detection_set = set(progress['no_detection_tiles']) | raw_no_detection

    # If a previously failed tile succeeds in a later retry, clear stale failure status.
    failed_set -= raw_completed
    # If a tile now has detections, clear stale no-detection status.
    no_detection_set -= (raw_completed - raw_no_detection)
    # Failed status takes precedence over no-detection status.
    no_detection_set -= raw_failed

    progress['completed_tiles'] = sorted(completed_set)
    progress['failed_tiles'] = sorted(failed_set)
    progress['no_detection_tiles'] = sorted(no_detection_set)

    batch_report = {
        'timestamp': utc_now_iso(),
        'run_id': run_id,
        'progress_log': log_file,
        'args': vars(args),
        'source_batch': [os.path.basename(p) for p in source_batch],
        'preprocess_failures': preprocess_failures,
        'detect_summary': {
            'processed_count': len(detect_processed),
            'failed_count': len(detect_failed),
            'no_detection_count': len(detect_no_detection),
            'missing_count': len(missing),
        },
        'raw_summary': {
            'completed_count': len(raw_completed),
            'failed_count': len(raw_failed),
            'no_detection_count': len(raw_no_detection),
        },
        'chip_merge_outputs': merged_outputs,
    }

    progress['processing_history'].append({
        'batch': len(progress['processing_history']) + 1,
        'count': len(source_batch),
        'completed': len(raw_completed),
        'failed': len(raw_failed),
        'no_detection': len(raw_no_detection),
        'timestamp': batch_report['timestamp'],
    })

    save_processing_progress(args.progress_file, progress)

    run_report_path = os.path.join('run_reports', f"run_{run_id}.json")
    save_json(run_report_path, batch_report)

    total_elapsed = time.time() - run_started_at
    log('=' * 80)
    log('Batch Complete')
    log('=' * 80)
    log(f"Source files in batch: {len(source_batch)}")
    log(f"Completed: {len(raw_completed)}")
    log(f"Failed: {len(raw_failed)}")
    log(f"No detections: {len(raw_no_detection)}")
    log(f"Total elapsed: {total_elapsed / 60.0:.2f} minutes")
    log(f"Run report: {run_report_path}")
    log(f"Progress file: {args.progress_file}")
    log(f"Results: {args.seg_res_path}")
    log(f"Progress log: {log_file}")

    if total_remaining > len(source_batch):
        log(f"{total_remaining - len(source_batch)} source files remain after this batch.")

    summarize_and_exit(has_failures=bool(raw_failed), allow_partial=args.allow_partial)


if __name__ == '__main__':
    main()
