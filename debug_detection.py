# Create debug_detection.py
import os
from tools.detect_scripts import detect_sentinel_batch

# Try processing just ONE tile with verbose output
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

# Get first tile
tiles = [f for f in os.listdir('imgs') if f.endswith('.tif')]
if not tiles:
    print("ERROR: No tiles in imgs/")
else:
    print(f"Testing with: {tiles[0]}")
    
    detect_sentinel_batch(
        ori_img_dir="imgs",
        img_list_file=[tiles[0]],  # Just the first one
        workdir="temp",
        seg_res_path="result_africa",
        model_cfg=model_cfg,
        **preprocess_cfg,
        **result_merge_cfg,
    )
    
    print("\nChecking results...")
    print(f"result_africa exists: {os.path.exists('result_africa')}")
    if os.path.exists('result_africa'):
        print(f"Contents: {os.listdir('result_africa')}")