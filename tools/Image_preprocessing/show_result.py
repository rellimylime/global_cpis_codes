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
import math


def _read_image_for_display(img_path):
    """
    Read GeoTIFF for visualization without skimage dependency.
    Returns HxWxC numpy array suitable for matplotlib.
    """
    ds = gdal.Open(img_path)
    if ds is None:
        raise RuntimeError(f"Could not open image: {img_path}")

    arr = ds.ReadAsArray()
    if arr is None:
        raise RuntimeError(f"Could not read image array: {img_path}")

    # GDAL returns CxHxW for multiband, HxW for single band.
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    elif arr.ndim == 3:
        arr = np.transpose(arr, (1, 2, 0))
        if arr.shape[2] == 1:
            arr = np.repeat(arr, 3, axis=2)
        elif arr.shape[2] > 3:
            arr = arr[:, :, :3]
    else:
        raise RuntimeError(f"Unexpected image shape {arr.shape} for {img_path}")

    return arr


def _save_mask_geotiff(mask, ref_img_path, out_path):
    """Save a uint8 mask as georeferenced GeoTIFF using reference image metadata."""
    src = gdal.Open(ref_img_path)
    if src is None:
        raise RuntimeError(f"Could not open reference image: {ref_img_path}")

    height, width = mask.shape
    driver = gdal.GetDriverByName('GTiff')
    out_ds = driver.Create(out_path, width, height, 1, gdal.GDT_Byte)
    if out_ds is None:
        raise RuntimeError(f"Could not create output GeoTIFF: {out_path}")

    out_ds.SetGeoTransform(src.GetGeoTransform())
    out_ds.SetProjection(src.GetProjection())
    out_band = out_ds.GetRasterBand(1)
    out_band.WriteArray(mask)
    out_band.SetNoDataValue(0)

    out_ds.FlushCache()
    out_ds = None
    src = None

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
        segms = [
            shapely.geometry.Polygon(np.array(s, dtype=float).reshape(-1, 2).tolist())
            for s in segm
            if s is not None and len(s) >= 6
        ]
        segms = [p for p in segms if p.is_valid and (not p.is_empty)]
        if not segms:
            return None
        areas = [p.area for p in segms]
        return segms[int(np.argmax(areas))]

    stdout_on()

    shp_path = os.path.join(save_path, "seg")
    os.makedirs(shp_path, mode=0o777, exist_ok=True)

    # 1) Build polygons + scores, skipping empty segmentations.
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

    # 2) For each threshold, union and draw.
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

        poly_list = []
        if unioned.geom_type == "Polygon":
            poly_list = [unioned]
        elif unioned.geom_type == "MultiPolygon":
            poly_list = list(unioned.geoms)
        elif unioned.geom_type == "GeometryCollection":
            candidates = [g for g in unioned.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
            flat = []
            for g in candidates:
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

        base = os.path.splitext(os.path.split(ori_img_path)[1])[0]
        image = _read_image_for_display(ori_img_path)
        height, width = image.shape[0], image.shape[1]
        mask = np.zeros((height, width), dtype=np.uint8)
        valid_poly_count = 0

        for p in poly_list:
            coords = list(p.exterior.coords)
            if len(coords) < 3:
                continue
            pts = np.array([[int(round(x)), int(round(y))] for x, y in coords], dtype=np.int32)
            if pts.shape[0] < 3:
                continue
            pts = pts.reshape((-1, 1, 2))
            cv2.fillPoly(mask, [pts], 255)
            valid_poly_count += 1

        if valid_poly_count == 0:
            print(f"No valid exterior rings to rasterize at score >= {st}. Skipping.")
            continue

        save_file = os.path.join(shp_path, base + f"union_segm_{st}.tif")
        _save_mask_geotiff(mask, ori_img_path, save_file)
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
    stdout_off()
    nms_cfg = dict(
        type='nms',
        iou_threshold=nms_iou_thr
    )

    seg_path = union_segm(
        js_data=result_json,
        nms_cfg=nms_cfg,
        merge_cats=nms_merge_cats,
        score_thr=score_thr,
        save_path=os.path.split(res_js_file)[0],
        ori_img_path=ori_img_path,
        ref_json = ref_json
    )

    return seg_path

