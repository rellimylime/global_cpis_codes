import shapely.geometry
import shapely.ops
from pycocotools.coco import COCO
from .save_read_geotiff import get_image_info
import json
import torch
import os
from osgeo import gdal
import numpy as np
import tqdm
from mmcv.ops.nms import batched_nms, nms_match
import copy
from tools.utils import stdout_off, stdout_on
import cv2
from pycocotools.coco import COCO
from skimage import io
from matplotlib import pyplot as plt
import math

def union_segm(
        js_data,
        nms_cfg,
        ori_img_path,
        ref_json,
        merge_cats=False,
        score_thr=[0.3, 0.85],
        save_path=None,
):
    # 0) no detections at all
    if not js_data:
        print("No detection results (empty js_data). Skipping visualization.")
        return None

    def __as_polygon(segm):
        # segm is list-of-lists, each inner list is flattened [x1,y1,x2,y2,...]
        segms = [
            shapely.geometry.Polygon(
                np.array(s, dtype=float).reshape(-1, 2).tolist()
            )
            for s in segm
            if s is not None and len(s) >= 6
        ]
        # filter invalid/empty polys
        segms = [p for p in segms if p.is_valid and (not p.is_empty)]
        if not segms:
            return None
        areas = [p.area for p in segms]
        return segms[int(np.argmax(areas))]

    stdout_on()

    shp_path = os.path.join(save_path, "seg")
    os.makedirs(shp_path, mode=0o777, exist_ok=True)

    # 1) build polygons + scores, skipping empty segmentations
    polys = []
    scores = []
    for j in js_data:
        segm = j.get("segmentation", None)
        if not segm:
            continue
        poly = __as_polygon(segm)
        if poly is None:
            continue
        polys.append(poly)
        scores.append(float(j.get("score", 0.0)))

    if not polys:
        print("No valid polygons after parsing. Skipping visualization.")
        return None

    score = np.array(scores, dtype=float)

    # 2) for each threshold, union and draw
    last_save_file = None
    for st in score_thr:
        idxs = score >= st
        keep = [p for keep_flag, p in zip(idxs, polys) if keep_flag]

        if not keep:
            print(f"No detections at score >= {st}. Skipping this threshold.")
            continue

        unioned = shapely.ops.unary_union(keep)
        if unioned.is_empty:
            print(f"Union is empty at score >= {st}. Skipping this threshold.")
            continue

        # Normalize unioned geometry into a list of Polygon objects
        poly_list = []
        if unioned.geom_type == "Polygon":
            poly_list = [unioned]
        elif unioned.geom_type == "MultiPolygon":
            poly_list = list(unioned.geoms)
        elif unioned.geom_type == "GeometryCollection":
            poly_list = [g for g in unioned.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
            # flatten any MultiPolygons inside the collection
            flat = []
            for g in poly_list:
                if g.geom_type == "Polygon":
                    flat.append(g)
                else:
                    flat.extend(list(g.geoms))
            poly_list = flat
        else:
            print(f"Union geometry type {unioned.geom_type} not supported. Skipping.")
            continue

        if not poly_list:
            print(f"No drawable polygons at score >= {st}. Skipping.")
            continue

        coco = COCO(ref_json)
        base = os.path.splitext(os.path.split(ori_img_path)[1])[0]
        image = io.imread(ori_img_path)

        seg = [{"segmentation": []}]

        # Each polygon exterior coords -> COCO expects [x1,y1,x2,y2,...]
        for p in poly_list:
            coords = list(p.exterior.coords)
            if len(coords) < 3:
                continue
            flat = []
            for x, y in coords:
                flat.append(float(x))
                flat.append(float(y))
            # COCO segmentation needs at least 3 points => 6 numbers
            if len(flat) >= 6:
                seg[0]["segmentation"].append(flat)

        if not seg[0]["segmentation"]:
            print(f"No valid exterior rings to draw at score >= {st}. Skipping.")
            continue

        fig, ax = plt.subplots()
        ax.imshow(image)
        coco.showAnns(seg)
        plt.axis("off")

        height, width = image.shape[0], image.shape[1]
        fig.set_size_inches(width / 100.0, height / 100.0)
        plt.gca().xaxis.set_major_locator(plt.NullLocator())
        plt.gca().yaxis.set_major_locator(plt.NullLocator())
        plt.subplots_adjust(top=1, bottom=0, left=0, right=1, hspace=0, wspace=0)
        plt.margins(0, 0)

        save_file = os.path.join(shp_path, base + f"union_segm_{st}.tif")
        plt.savefig(save_file)
        plt.close(fig)

        last_save_file = save_file

    return last_save_file


def detect_result_to_json(
        res_js_file,
        dataset_js_file,
        dataset_img_path,
):
    cocoGt = COCO(dataset_js_file)

    if 'info' not in cocoGt.dataset:
        cocoGt.dataset['info'] = {}

    try:
        cocoDt = cocoGt.loadRes(res_js_file)
    except IndexError:
        print('The testing results of the whole dataset is empty.')
        cocoDt = COCO()
    im_geotrans = dict()
    for i, img in cocoDt.imgs.items():
        img_file = dataset_img_path
        _, _, _, im_geotran, _ = get_image_info(img_file)
        im_geotrans[i] = list(im_geotran)

    res_json = []
    for i, ann in cocoDt.anns.items():
        img_id = ann["image_id"]
        bbox = ann["bbox"]

        if ann.get("segmentation", None) is None:
            json_temp = dict(
                image_id=img_id,
                bbox=bbox,
                score=ann["score"],
                category_id=ann["category_id"]
            )
        else:
            mask = cocoDt.annToMask(ann)
            contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            polygon = [cont.flatten() for cont in contours]

            geo_segm = []
            for p in polygon:
                xs = p[::2]
                ys = p[1::2]
                segm = np.array([[x, y] for x, y in zip(xs, ys)]).flatten().tolist()
                geo_segm.append(segm)
            json_temp = dict(
                image_id=img_id,
                bbox=bbox,
                score=ann["score"],
                category_id=ann["category_id"],
                segmentation=geo_segm
            )
        res_json.append(json_temp)

    return res_json


def show_result(
    res_js_file,
    dataset_js_file,
    dataset_img_path,
    ori_img_path,
    ref_json,
    nms_merge_cats,
    nms_iou_thr = 0.5,
    score_thr = [0.3, 0.85],

):
    result_json = detect_result_to_json(
        res_js_file,
        dataset_js_file,
        dataset_img_path
    )

    # NMS
    print("3.NMS.", end=' ')
    nms_cfg = dict(type='nms', iou_threshold=nms_iou_thr)

    try:
        stdout_off()
        seg_path = union_segm(
            js_data=result_json,
            nms_cfg=nms_cfg,
            merge_cats=nms_merge_cats,
            score_thr=score_thr,
            save_path=os.path.split(res_js_file)[0],
            ori_img_path=ori_img_path,
            ref_json=ref_json
        )
    finally:
        stdout_on()

    if seg_path is None:
        print("No detections after postprocess (seg_path=None).")
    else:
        print("done.")

    return seg_path