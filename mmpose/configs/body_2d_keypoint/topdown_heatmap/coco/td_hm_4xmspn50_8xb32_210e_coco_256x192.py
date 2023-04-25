# Copyright (c) OpenMMLab. All rights reserved.
if '_base_':
    from ...._base_.default_runtime import *

from mmengine.dataset.sampler import DefaultSampler
from mmengine.optim.scheduler.lr_scheduler import LinearLR, MultiStepLR
from torch.optim.adam import Adam

from mmpose.codecs.megvii_heatmap import MegviiHeatmap
from mmpose.datasets.datasets.body.coco_dataset import CocoDataset
from mmpose.datasets.transforms.common_transforms import (GenerateTarget,
                                                          GetBBoxCenterScale,
                                                          RandomBBoxTransform,
                                                          RandomFlip,
                                                          RandomHalfBody)
from mmpose.datasets.transforms.formatting import PackPoseInputs
from mmpose.datasets.transforms.loading import LoadImage
from mmpose.datasets.transforms.topdown_transforms import TopdownAffine
from mmpose.evaluation.metrics.coco_metric import CocoMetric
from mmpose.models.backbones.mspn import MSPN
from mmpose.models.data_preprocessors.data_preprocessor import \
    PoseDataPreprocessor
from mmpose.models.heads.heatmap_heads.mspn_head import MSPNHead
from mmpose.models.losses.heatmap_loss import (KeypointMSELoss,
                                               KeypointOHKMMSELoss)
from mmpose.models.pose_estimators.topdown import TopdownPoseEstimator

# runtime
train_cfg.merge(dict(max_epochs=210, val_interval=10))

# optimizer
optim_wrapper = dict(optimizer=dict(
    type=Adam,
    lr=5e-3,
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
auto_scale_lr = dict(base_batch_size=256)

# hooks
default_hooks.merge(dict(checkpoint=dict(save_best='coco/AP', rule='greater')))

# codec settings
# multiple kernel_sizes of heatmap gaussian for 'Megvii' approach.
kernel_sizes = [15, 11, 9, 7, 5]
codec = [
    dict(
        type=MegviiHeatmap,
        input_size=(192, 256),
        heatmap_size=(48, 64),
        kernel_size=kernel_size) for kernel_size in kernel_sizes
]

# model settings
model = dict(
    type=TopdownPoseEstimator,
    data_preprocessor=dict(
        type=PoseDataPreprocessor,
        mean=[123.675, 116.28, 103.53],
        std=[58.395, 57.12, 57.375],
        bgr_to_rgb=True),
    backbone=dict(
        type=MSPN,
        unit_channels=256,
        num_stages=4,
        num_units=4,
        num_blocks=[3, 4, 6, 3],
        norm_cfg=dict(type='BN'),
        init_cfg=dict(
            type='Pretrained',
            checkpoint='torchvision://resnet50',
        )),
    head=dict(
        type=MSPNHead,
        out_shape=(64, 48),
        unit_channels=256,
        out_channels=17,
        num_stages=4,
        num_units=4,
        norm_cfg=dict(type='BN'),
        # each sub list is for a stage
        # and each element in each list is for a unit
        level_indices=[0, 1, 2, 3] * 3 + [1, 2, 3, 4],
        loss=([
            dict(
                type=KeypointMSELoss, use_target_weight=True, loss_weight=0.25)
        ] * 3 + [
            dict(
                type=KeypointOHKMMSELoss,
                use_target_weight=True,
                loss_weight=1.)
        ]) * 4,
        decoder=codec[-1]),
    test_cfg=dict(
        flip_test=True,
        flip_mode='heatmap',
        shift_heatmap=False,
    ))

# base dataset settings
dataset_type = 'CocoDataset'
data_mode = 'topdown'
data_root = 'data/coco/'

# pipelines
train_pipeline = [
    dict(type=LoadImage),
    dict(type=GetBBoxCenterScale),
    dict(type=RandomFlip, direction='horizontal'),
    dict(type=RandomHalfBody),
    dict(type=RandomBBoxTransform),
    dict(type=TopdownAffine, input_size=codec[0]['input_size']),
    dict(type=GenerateTarget, multilevel=True, encoder=codec),
    dict(type=PackPoseInputs)
]
val_pipeline = [
    dict(type=LoadImage),
    dict(type=GetBBoxCenterScale),
    dict(type=TopdownAffine, input_size=codec[0]['input_size']),
    dict(type=PackPoseInputs)
]

# data loaders
train_dataloader = dict(
    batch_size=32,
    num_workers=4,
    persistent_workers=True,
    sampler=dict(type=DefaultSampler, shuffle=True),
    dataset=dict(
        type=CocoDataset,
        data_root=data_root,
        data_mode=data_mode,
        ann_file='annotations/person_keypoints_train2017.json',
        data_prefix=dict(img='train2017/'),
        pipeline=train_pipeline,
    ))
val_dataloader = dict(
    batch_size=32,
    num_workers=4,
    persistent_workers=True,
    drop_last=False,
    sampler=dict(type=DefaultSampler, shuffle=False, round_up=False),
    dataset=dict(
        type=CocoDataset,
        data_root=data_root,
        data_mode=data_mode,
        ann_file='annotations/person_keypoints_val2017.json',
        bbox_file='data/coco/person_detection_results/'
        'COCO_val2017_detections_AP_H_56_person.json',
        data_prefix=dict(img='val2017/'),
        test_mode=True,
        pipeline=val_pipeline,
    ))
test_dataloader = val_dataloader

# evaluators
val_evaluator = dict(
    type=CocoMetric,
    ann_file=data_root + 'annotations/person_keypoints_val2017.json',
    nms_mode='none')
test_evaluator = val_evaluator
