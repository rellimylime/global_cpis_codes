
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

    img_list = [
        os.path.join(ori_img_dir, img.strip('\n'))
        for img in img_list_file
        if img.strip('\n').lower().endswith('.tif')
    ]
    print("done.")

    # build model.
    print("2.build model.", end=' ', flush=True)
    try:
        stdout_off()
        model = build_mmdet_model(model_cfg)
    except Exception:
        stdout_on()
        print("\nModel build failed. Traceback:\n", flush=True)
        traceback.print_exc()
        raise
    finally:
        # Always restore stdout even if build fails.
        stdout_on()
    print("done.", flush=True)

    # Detect images
    print("3. Detect images.")
    seg_paths = []
    fail_img = []
    fail_tracebacks = []
    no_result_img = []
    total_imgs = len(img_list)
    for idx, img_file in enumerate(img_list, 1):
        st = time.time()
        img_base = os.path.basename(img_file)
        print(f"[{idx}/{total_imgs}] {img_base}")
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
            if seg_path is not None:
                seg_paths.append((img_file, seg_path))
                print("  status: detected")
            else:
                no_result_img.append(f"{img_file}\tNo detections\n")
                print("  status: no_detection")
        except Exception as e:
            fail_img.append(f"{img_file}\t{repr(e)}\n")
            fail_tracebacks.append(
                f"===== {img_file} =====\n{traceback.format_exc()}\n"
            )
            print(f"  status: failed ({e})")

        print(f"  processing time: {time.strftime('%H:%M:%S', time.gmtime(time.time()-st))}")

    # Merge all image result.
    print("4.Merge all image result.", end=' ')
    os.makedirs(seg_res_path, mode=0o777, exist_ok=True)
    for img_file, seg_file in seg_paths:
        img_name = os.path.splitext(os.path.basename(img_file))[0]
        to_dir = os.path.join(seg_res_path, img_name)
        from_dir = os.path.dirname(seg_file)
        if os.path.exists(to_dir):
            shutil.rmtree(to_dir, ignore_errors=True)
        shutil.copytree(from_dir, to_dir)
    shutil.rmtree(workdir, ignore_errors=True)
    print('done.')

    print("5.save failed image list.", end=' ')
    fail_list_file = os.path.join(seg_res_path, "fail_img.txt")
    with open(fail_list_file, "w") as f:
        f.writelines(fail_img)
    fail_trace_file = os.path.join(seg_res_path, "fail_tracebacks.txt")
    with open(fail_trace_file, "w") as f:
        f.writelines(fail_tracebacks)
    no_result_file = os.path.join(seg_res_path, "no_detection_img.txt")
    with open(no_result_file, "w") as f:
        f.writelines(no_result_img)
    print("done.")

    return {
        "processed": [os.path.basename(p[0]) for p in seg_paths],
        "failed": [os.path.basename(line.split("\t", 1)[0]) for line in fail_img],
        "no_detection": [os.path.basename(line.split("\t", 1)[0]) for line in no_result_img],
    }
