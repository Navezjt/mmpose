# Copyright (c) OpenMMLab. All rights reserved.
if '_base_':
    from ...._base_.default_runtime import *

from mmengine.dataset.sampler import DefaultSampler
from mmengine.optim.scheduler.lr_scheduler import LinearLR, MultiStepLR
from torch.optim.adam import Adam

from mmpose.codecs.msra_heatmap import MSRAHeatmap
from mmpose.datasets.datasets.face.coco_wholebody_face_dataset import \
    CocoWholeBodyFaceDataset
from mmpose.datasets.transforms.common_transforms import (GenerateTarget,
                                                          GetBBoxCenterScale,
                                                          RandomBBoxTransform,
                                                          RandomFlip)
from mmpose.datasets.transforms.formatting import PackPoseInputs
from mmpose.datasets.transforms.loading import LoadImage
from mmpose.datasets.transforms.topdown_transforms import TopdownAffine
from mmpose.evaluation.metrics.keypoint_2d_metrics import NME
from mmpose.models.backbones.mobilenet_v2 import MobileNetV2
from mmpose.models.data_preprocessors.data_preprocessor import \
    PoseDataPreprocessor
from mmpose.models.heads.heatmap_heads.heatmap_head import HeatmapHead
from mmpose.models.losses.heatmap_loss import KeypointMSELoss
from mmpose.models.pose_estimators.topdown import TopdownPoseEstimator

# runtime
train_cfg.merge(dict(max_epochs=60, val_interval=1))

# optimizer
optim_wrapper = dict(optimizer=dict(
    type=Adam,
    lr=2e-3,
))

# learning policy
param_scheduler = [
    dict(type=LinearLR, begin=0, end=500, start_factor=0.001,
         by_epoch=False),  # warm-up
    dict(
        type=MultiStepLR,
        begin=0,
        end=210,
        milestones=[40, 55],
        gamma=0.1,
        by_epoch=True)
]

# automatically scaling LR based on the actual training batch size
auto_scale_lr = dict(base_batch_size=256)

# hooks
default_hooks.merge(
    dict(checkpoint=dict(save_best='NME', rule='less', interval=1)))

# codec settings
codec = dict(
    type=MSRAHeatmap, input_size=(256, 256), heatmap_size=(64, 64), sigma=2)

# model settings
model = dict(
    type=TopdownPoseEstimator,
    data_preprocessor=dict(
        type=PoseDataPreprocessor,
        mean=[123.675, 116.28, 103.53],
        std=[58.395, 57.12, 57.375],
        bgr_to_rgb=True),
    backbone=dict(
        type=MobileNetV2,
        widen_factor=1.,
        out_indices=(7, ),
        init_cfg=dict(type='Pretrained', checkpoint='mmcls://mobilenet_v2')),
    head=dict(
        type=HeatmapHead,
        in_channels=1280,
        out_channels=68,
        loss=dict(type=KeypointMSELoss, use_target_weight=True),
        decoder=codec),
    test_cfg=dict(
        flip_test=True,
        flip_mode='heatmap',
        shift_heatmap=True,
    ))

# base dataset settings
dataset_type = 'CocoWholeBodyFaceDataset'
data_mode = 'topdown'
data_root = 'data/coco/'

# pipelines
train_pipeline = [
    dict(type=LoadImage),
    dict(type=GetBBoxCenterScale),
    dict(type=RandomFlip, direction='horizontal'),
    dict(
        type=RandomBBoxTransform, rotate_factor=60, scale_factor=(0.75, 1.25)),
    dict(type=TopdownAffine, input_size=codec['input_size']),
    dict(type=GenerateTarget, encoder=codec),
    dict(type=PackPoseInputs)
]
val_pipeline = [
    dict(type=LoadImage),
    dict(type=GetBBoxCenterScale),
    dict(type=TopdownAffine, input_size=codec['input_size']),
    dict(type=PackPoseInputs)
]

# data loaders
train_dataloader = dict(
    batch_size=32,
    num_workers=2,
    persistent_workers=True,
    sampler=dict(type=DefaultSampler, shuffle=True),
    dataset=dict(
        type=CocoWholeBodyFaceDataset,
        data_root=data_root,
        data_mode=data_mode,
        ann_file='annotations/coco_wholebody_train_v1.0.json',
        data_prefix=dict(img='train2017/'),
        pipeline=train_pipeline,
    ))
val_dataloader = dict(
    batch_size=32,
    num_workers=2,
    persistent_workers=True,
    drop_last=False,
    sampler=dict(type=DefaultSampler, shuffle=False, round_up=False),
    dataset=dict(
        type=CocoWholeBodyFaceDataset,
        data_root=data_root,
        data_mode=data_mode,
        ann_file='annotations/coco_wholebody_val_v1.0.json',
        data_prefix=dict(img='val2017/'),
        test_mode=True,
        pipeline=val_pipeline,
    ))
test_dataloader = val_dataloader

# evaluators
val_evaluator = dict(
    type=NME,
    norm_mode='keypoint_distance',
)
test_evaluator = val_evaluator
