# batch_detect_africa.py
import os
import sys
import argparse
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import warnings
warnings.filterwarnings('ignore')

# Import your toolscript from the repo
from tools.detect_scripts import detect_sentinel_batch

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--auto', action='store_true')
    parser.add_argument('--img_dir', type=str, required=True, 
                        help="Directory containing scaled images")
    args = parser.parse_args()

    # Directories
    ori_img_dir = args.img_dir
    workdir = "temp"
    seg_res_path = "result_africa"
    
    # Fix #6: Strict usage of _batch_list.txt
    # We do NOT filter by arid shapefiles or check 'completed' JSONs here.
    # The pipeline_master.py has already done that work.
    list_file = os.path.join(ori_img_dir, "_batch_list.txt")
    
    if not os.path.exists(list_file):
        print(f"Error: {list_file} not found.")
        sys.exit(1) # Return error code so pipeline knows to stop

    with open(list_file, "r") as f:
        # Read filenames exactly as written by pipeline
        batch_tiles = [line.strip() for line in f if line.strip()]

    if not batch_tiles:
        print("Batch list is empty. Nothing to detect.")
        sys.exit(0)

    print(f"Loaded {len(batch_tiles)} files from batch list.")

    # Model Configuration (unchanged)
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

    try:
        # Run detection
        detect_sentinel_batch(
            ori_img_dir=ori_img_dir,
            img_list_file=batch_tiles,
            workdir=workdir,
            seg_res_path=seg_res_path,
            model_cfg=model_cfg,
            **preprocess_cfg,
            **result_merge_cfg,
        )
        print("Batch processing success.")
        
    except Exception as e:
        print(f"Detection Error: {e}")
        # Fix #4: Critical exit code so pipeline stops
        sys.exit(1)

if __name__ == '__main__':
    main()