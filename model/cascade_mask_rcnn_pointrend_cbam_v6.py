"""V6 training config — fixed LR schedule + vertical flip augmentation.

Changes from cascade_mask_rcnn_pointrend_cbam.py:
  - total_epochs: 140 → 36  (LR decay now fires within budget)
  - lr_config.step: [40]   → [24, 32]  (two decays: 1e-3 → 1e-4 → 1e-5)
  - lr_config.warmup_iters: 100 → 200  (longer warmup for fine-tuning stability)
  - train_pipeline: added vertical RandomFlip in addition to horizontal
    (CPIs are circles → rotation-invariant; 4-fold flip covers ×4 symmetry)

Everything else (architecture, augmentation scales, optimizer, etc.) is unchanged.
"""

_base_ = "cascade_mask_rcnn_pointrend_cbam.py"

# ---- LR schedule: two step-decays within 36-epoch budget ----
total_epochs = 36
lr_config = dict(
    policy="step",
    warmup="linear",
    warmup_iters=200,
    warmup_ratio=0.0005,
    step=[24, 32],
)

# ---- Augmentation: add vertical flip on top of existing horizontal ----
# The base config already has multi-scale resize + horizontal flip.
# We override the full train pipeline to add a second RandomFlip (vertical).
img_norm_cfg = dict(
    mean=[162.966, 167.877, 168.011, 181.276],
    std=[71.607, 72.094, 74.471, 62.717],
    to_rgb=False,
)

train_pipeline = [
    dict(type="LoadMultiBandsImageFromFile", img_mode="1234"),
    dict(type="LoadAnnotations", with_bbox=True, with_mask=True),
    dict(
        type="Resize",
        img_scale=[(800, 480), (1000, 600), (1200, 720)],
        multiscale_mode="value",
        keep_ratio=True,
    ),
    dict(type="RandomFlip", flip_ratio=0.5, direction="horizontal"),
    dict(type="RandomFlip", flip_ratio=0.5, direction="vertical"),
    dict(
        type="Normalize",
        mean=[162.966, 167.877, 168.011, 181.276],
        std=[71.607, 72.094, 74.471, 62.717],
        to_rgb=False,
    ),
    dict(type="Pad", size_divisor=32),
    dict(type="DefaultFormatBundle"),
    dict(type="Collect", keys=["img", "gt_bboxes", "gt_labels", "gt_masks"]),
]

data = dict(
    samples_per_gpu=2,
    workers_per_gpu=0,
    train=dict(pipeline=train_pipeline),
)
