import torch
from mmcv import Config
from mmcv.parallel import MMDataParallel, MMDistributedDataParallel
from mmcv.runner import (init_dist, load_checkpoint,
                         wrap_fp16_model)

from mmdet.models import build_detector


def build_mmdet_model(
        cfgs
):
    cfg_file = cfgs['cfg_file']
    checkpoint = cfgs['checkpoint']
    infer_score_thr = cfgs.get('infer_score_thr', None)
    infer_nms_iou = cfgs.get('infer_nms_iou', None)
    infer_max_per_img = cfgs.get('infer_max_per_img', None)
    infer_mask_thr_binary = cfgs.get('infer_mask_thr_binary', None)
    fuse_conv_bn = False
    launcher = 'none'

    cfg = Config.fromfile(cfg_file)
    # import modules from string list.
    if cfg.get('custom_imports', None):
        from mmcv.utils import import_modules_from_strings
        import_modules_from_strings(**cfg['custom_imports'])
    # set cudnn_benchmark
    if cfg.get('cudnn_benchmark', False):
        torch.backends.cudnn.benchmark = True
    cfg.model.pretrained = None
    if cfg.model.get('neck'):
        if isinstance(cfg.model.neck, list):
            for neck_cfg in cfg.model.neck:
                if neck_cfg.get('rfp_backbone'):
                    if neck_cfg.rfp_backbone.get('pretrained'):
                        neck_cfg.rfp_backbone.pretrained = None
        elif cfg.model.neck.get('rfp_backbone'):
            if cfg.model.neck.rfp_backbone.get('pretrained'):
                cfg.model.neck.rfp_backbone.pretrained = None

    # in case the test dataset is concatenated
    if isinstance(cfg.data.test, dict):
        cfg.data.test.test_mode = True
    elif isinstance(cfg.data.test, list):
        for ds_cfg in cfg.data.test:
            ds_cfg.test_mode = True

    # Optional runtime overrides to trade precision/recall without editing model file.
    if hasattr(cfg, 'test_cfg') and hasattr(cfg.test_cfg, 'rcnn'):
        if infer_score_thr is not None:
            cfg.test_cfg.rcnn.score_thr = float(infer_score_thr)
        if infer_nms_iou is not None and hasattr(cfg.test_cfg.rcnn, 'nms'):
            cfg.test_cfg.rcnn.nms.iou_threshold = float(infer_nms_iou)
        if infer_max_per_img is not None:
            cfg.test_cfg.rcnn.max_per_img = int(infer_max_per_img)
        if infer_mask_thr_binary is not None:
            cfg.test_cfg.rcnn.mask_thr_binary = float(infer_mask_thr_binary)

    # init distributed env first, since logger depends on the dist info.
    if launcher == 'none':
        distributed = False
    else:
        distributed = True
        init_dist(launcher, **cfg.dist_params)

    # build the model and load checkpoint
    model = build_detector(cfg.model, train_cfg=None, test_cfg=cfg.test_cfg)
    fp16_cfg = cfg.get('fp16', None)
    if fp16_cfg is not None and torch.cuda.is_available():
        wrap_fp16_model(model)
    checkpoint = load_checkpoint(model, checkpoint, map_location='cpu')
    if fuse_conv_bn:
        model = fuse_conv_bn(model)
    # old versions did not save class info in checkpoints, this walkaround is
    # for backward compatibility
    if 'CLASSES' in checkpoint['meta']:
        model.CLASSES = checkpoint['meta']['CLASSES']

    if not distributed:
        model = MMDataParallel(model, device_ids=[0])
    else:
        model = MMDistributedDataParallel(
            model.cuda(),
            device_ids=[torch.cuda.current_device()],
            broadcast_buffers=False)

    return model

