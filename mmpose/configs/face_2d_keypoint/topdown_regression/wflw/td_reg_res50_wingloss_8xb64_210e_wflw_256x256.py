# Copyright (c) OpenMMLab. All rights reserved.
if '_base_':
    from ...._base_.default_runtime import *

from mmengine.dataset.sampler import DefaultSampler
from mmengine.optim.scheduler.lr_scheduler import LinearLR, MultiStepLR
from torch.optim.adam import Adam

from mmpose.codecs.regression_label import RegressionLabel
from mmpose.datasets.datasets.face.wflw_dataset import WFLWDataset
from mmpose.datasets.transforms.common_transforms import (GenerateTarget,
                                                          GetBBoxCenterScale,
                                                          RandomBBoxTransform,
                                                          RandomFlip)
from mmpose.datasets.transforms.formatting import PackPoseInputs
from mmpose.datasets.transforms.loading import LoadImage
from mmpose.datasets.transforms.topdown_transforms import TopdownAffine
from mmpose.evaluation.metrics.keypoint_2d_metrics import NME
from mmpose.models.backbones.resnet import ResNet
from mmpose.models.data_preprocessors.data_preprocessor import \
    PoseDataPreprocessor
from mmpose.models.heads.regression_heads.regression_head import RegressionHead
from mmpose.models.losses.regression_loss import WingLoss
from mmpose.models.necks.gap_neck import GlobalAveragePooling
from mmpose.models.pose_estimators.topdown import TopdownPoseEstimator

# runtime
train_cfg.merge(dict(max_epochs=210, val_interval=10))

# optimizer
optim_wrapper = dict(optimizer=dict(
    type=Adam,
    lr=5e-4,
))

# learning policy
param_scheduler = [
    dict(type=LinearLR, begin=0, end=500, start_factor=0.001,
         by_epoch=False),  # warm-up
    dict(
        type=MultiStepLR,
        begin=0,
        end=210,
        milestones=[170, 200],
        gamma=0.1,
        by_epoch=True)
]

# automatically scaling LR based on the actual training batch size
auto_scale_lr = dict(base_batch_size=512)

# codec settings
codec = dict(type=RegressionLabel, input_size=(256, 256))

# model settings
model = dict(
    type=TopdownPoseEstimator,
    data_preprocessor=dict(
        type=PoseDataPreprocessor,
        mean=[123.675, 116.28, 103.53],
        std=[58.395, 57.12, 57.375],
        bgr_to_rgb=True),
    backbone=dict(
        type=ResNet,
        depth=50,
        init_cfg=dict(type='Pretrained', checkpoint='torchvision://resnet50'),
    ),
    neck=dict(type=GlobalAveragePooling),
    head=dict(
        type=RegressionHead,
        in_channels=2048,
        num_joints=98,
        loss=dict(type=WingLoss, use_target_weight=True),
        decoder=codec),
    train_cfg=dict(),
    test_cfg=dict(
        flip_test=True,
        shift_coords=True,
    ))

# base dataset settings
dataset_type = 'WFLWDataset'
data_mode = 'topdown'
data_root = 'data/wflw/'

# pipelines
train_pipeline = [
    dict(type=LoadImage),
    dict(type=GetBBoxCenterScale),
    dict(type=RandomFlip, direction='horizontal'),
    dict(
        type=RandomBBoxTransform, scale_factor=[0.75, 1.25], rotate_factor=60),
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

# dataloaders
train_dataloader = dict(
    batch_size=64,
    num_workers=2,
    persistent_workers=True,
    sampler=dict(type=DefaultSampler, shuffle=True),
    dataset=dict(
        type=WFLWDataset,
        data_root=data_root,
        data_mode=data_mode,
        ann_file='annotations/face_landmarks_wflw_train.json',
        data_prefix=dict(img='images/'),
        pipeline=train_pipeline,
    ))
val_dataloader = dict(
    batch_size=32,
    num_workers=2,
    persistent_workers=True,
    drop_last=False,
    sampler=dict(type=DefaultSampler, shuffle=False, round_up=False),
    dataset=dict(
        type=WFLWDataset,
        data_root=data_root,
        data_mode=data_mode,
        ann_file='annotations/face_landmarks_wflw_test.json',
        data_prefix=dict(img='images/'),
        test_mode=True,
        pipeline=val_pipeline,
    ))
test_dataloader = val_dataloader

# hooks
default_hooks.merge(dict(checkpoint=dict(save_best='NME', rule='less')))

# evaluators
val_evaluator = dict(
    type=NME,
    norm_mode='keypoint_distance',
)
test_evaluator = val_evaluator
