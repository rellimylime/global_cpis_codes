
from .detect_sentinel import detect_sentinel
from tools.sentinel_scripts.build_model import build_mmdet_model
from tools.utils import stdout_off, stdout_on
import os
import shutil
import time
import traceback


def detect_sentinel_batch(
        ori_img_dir,
        img_list_file,
        workdir,
        model_cfg,
        ref_dataset_json,
        nms_thr,
        nms_merge_cats,
        score_thr,
        seg_res_path
):
    # load image list
    print("1.load image list.", end=' ')

    img_list = [os.path.join(ori_img_dir, img.strip('\n')) for img in img_list_file if img.strip('\n').endswith('.tif')]
    print("done.")

    # build model.
    print("2.build model.", end=' ', flush=True)
    try:
        stdout_off()
        model = build_mmdet_model(model_cfg)
    except Exception:
        # ensure we can see the error
        stdout_on()
        print("\nModel build failed. Traceback:\n", flush=True)
        traceback.print_exc()
        raise
    finally:
        # ALWAYS restore stdout
        stdout_on()

    print("done.", flush=True)

    # Detect images
    print("3. Detect images.")
    seg_paths = []
    fail_img = []
    
    for img_file in img_list:
        st = time.time()
        try:
            seg_path = detect_sentinel(
                img_path=img_file,
                ref_json=ref_dataset_json,
                work_dir=workdir,
                nms_thr=nms_thr,
                nms_merge_cats=nms_merge_cats,
                score_thr=score_thr,
                model=model,
                model_cfg=model_cfg,
            )

            # seg_path can be None (no detections), that is not a failure
            if seg_path is not None:
                seg_paths.append((img_file, seg_path))

        except Exception as e:
            fail_img.append(f"{img_file}\t{repr(e)}\n")
            print(f"✗ FAILED {os.path.basename(img_file)}: {e}")

        print(f"Processing time: {time.strftime('%H:%M:%S', time.gmtime(time.time()-st))}")

    # Merge all image result.
    print("4.Merge all image result.", end=' ')
    os.makedirs(seg_res_path, mode=0o777, exist_ok=True)

    for img_file, seg_file in seg_paths:
        img_name = os.path.splitext(os.path.basename(img_file))[0]
        to_dir = os.path.join(seg_res_path, img_name)

        # seg_file is something like ".../seg/<img>union_segm_0.3.tif"
        from_dir = os.path.dirname(seg_file)

        if os.path.exists(to_dir):
            shutil.rmtree(to_dir, ignore_errors=True)

        shutil.copytree(from_dir, to_dir)

    print("done.")

    print("5.save failed image list.", end=' ')
    fail_list_file =  "fail_img.txt"
    with open(fail_list_file, "w") as f:
        f.writelines(fail_img)
    print("done.")




    pass
