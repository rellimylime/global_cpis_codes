import torch
from mmcv import Config
from mmcv.parallel import MMDataParallel, MMDistributedDataParallel
from mmcv.runner import init_dist, load_checkpoint, wrap_fp16_model
from mmdet.models import build_detector


def build_mmdet_model(cfgs):
    cfg_file = cfgs["cfg_file"]
    ckpt_path = cfgs["checkpoint"]  # path to checkpoint file

    fuse_conv_bn = False
    launcher = "none"

    cfg = Config.fromfile(cfg_file)

    # import modules from string list.
    if cfg.get("custom_imports", None):
        from mmcv.utils import import_modules_from_strings
        import_modules_from_strings(**cfg["custom_imports"])

    # Only relevant if CUDA exists
    if cfg.get("cudnn_benchmark", False) and torch.cuda.is_available():
        torch.backends.cudnn.benchmark = True

    # Disable pretrained weights in config
    cfg.model.pretrained = None
    if cfg.model.get("neck"):
        if isinstance(cfg.model.neck, list):
            for neck_cfg in cfg.model.neck:
                if neck_cfg.get("rfp_backbone") and neck_cfg.rfp_backbone.get("pretrained"):
                    neck_cfg.rfp_backbone.pretrained = None
        elif cfg.model.neck.get("rfp_backbone") and cfg.model.neck.rfp_backbone.get("pretrained"):
            cfg.model.neck.rfp_backbone.pretrained = None

    # in case the test dataset is concatenated
    if isinstance(cfg.data.test, dict):
        cfg.data.test.test_mode = True
    elif isinstance(cfg.data.test, list):
        for ds_cfg in cfg.data.test:
            ds_cfg.test_mode = True

    # init distributed env first, since logger depends on the dist info.
    if launcher == "none":
        distributed = False
    else:
        distributed = True
        init_dist(launcher, **cfg.dist_params)

    # Decide device
    use_cuda = torch.cuda.is_available()
    device = torch.device("cuda:0" if use_cuda else "cpu")

    # Build model and load checkpoint
    model = build_detector(cfg.model, train_cfg=None, test_cfg=cfg.test_cfg)

    fp16_cfg = cfg.get("fp16", None)
    if fp16_cfg is not None and use_cuda:
        wrap_fp16_model(model)

    ckpt = load_checkpoint(model, ckpt_path, map_location=device)

    if fuse_conv_bn:
        model = fuse_conv_bn(model)

    # old versions did not save class info in checkpoints, this workaround is
    # for backward compatibility
    if isinstance(ckpt, dict) and "meta" in ckpt and "CLASSES" in ckpt["meta"]:
        model.CLASSES = ckpt["meta"]["CLASSES"]

    # Move model to the right device
    model.to(device)
    model.eval()

    # Wrap only when CUDA is present
    if distributed:
        if not use_cuda:
            raise RuntimeError("Distributed mode requested but CUDA is not available.")
        model = MMDistributedDataParallel(
            model,
            device_ids=[torch.cuda.current_device()],
            broadcast_buffers=False,
        )
    else:
        if use_cuda:
            model = MMDataParallel(model, device_ids=[0])
        # else: leave as plain CPU model

    return model
