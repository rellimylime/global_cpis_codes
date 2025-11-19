"""
Batch CPI detection for all of Africa.

This script processes all downloaded Sentinel-2 images and runs
the CPI detection model on them.

Usage:
    python batch_detect_africa.py
"""

import os
from tools.detect_scripts import detect_sentinel_batch


def main():
    """Run CPI detection on all images in imgs/ directory."""

    print("=" * 80)
    print("Batch CPI Detection for Africa")
    print("=" * 80)

    # Model configuration (same as demo.py)
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
        print("Please process Sentinel-2 images first:")
        print("  python process_sentinel2_bands.py sentinel2_products/")
        return

    img_list = [f for f in os.listdir(ori_img_dir) if f.endswith('.tif')]

    if len(img_list) == 0:
        print(f"\nERROR: No .tif files found in {ori_img_dir}/")
        print("Please add processed Sentinel-2 images to this directory.")
        return

    print(f"\nFound {len(img_list)} images to process")
    print(f"Input directory: {ori_img_dir}/")
    print(f"Output directory: {seg_res_path}/")

    est_time_hours = len(img_list) * 2 / 60  # ~2 min per image
    print(f"\nEstimated processing time: ~{est_time_hours:.1f} hours")

    response = input("\nContinue? (yes/no): ")
    if response.lower() != 'yes':
        print("Cancelled.")
        return

    print("\n" + "=" * 80)
    print("Starting detection...")
    print("=" * 80)

    # Run detection
    detect_sentinel_batch(
        ori_img_dir=ori_img_dir,
        img_list_file=img_list,
        workdir=workdir,
        seg_res_path=seg_res_path,
        model_cfg=model_cfg,
        **preprocess_cfg,
        **result_merge_cfg,
    )

    print("\n" + "=" * 80)
    print("Detection Complete!")
    print("=" * 80)
    print(f"\nResults saved to: {seg_res_path}/")
    print("\nNext steps:")
    print("1. Review results in the output directory")
    print("2. Merge results from all tiles if needed")
    print("3. Create summary statistics/maps")


if __name__ == '__main__':
    main()
