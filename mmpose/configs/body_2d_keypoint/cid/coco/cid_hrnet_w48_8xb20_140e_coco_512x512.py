# Copyright (c) OpenMMLab. All rights reserved.
if '_base_':
    from ...._base_.default_runtime import *

from mmengine.dataset.sampler import DefaultSampler
from mmengine.optim.scheduler.lr_scheduler import MultiStepLR
from torch.optim.adam import Adam

from mmpose.codecs.decoupled_heatmap import DecoupledHeatmap
from mmpose.datasets.datasets.body.coco_dataset import CocoDataset
from mmpose.datasets.transforms.bottomup_transforms import (
    BottomupGetHeatmapMask, BottomupRandomAffine, BottomupResize)
from mmpose.datasets.transforms.common_transforms import (GenerateTarget,
                                                          RandomFlip)
from mmpose.datasets.transforms.formatting import PackPoseInputs
from mmpose.datasets.transforms.loading import LoadImage
from mmpose.evaluation.metrics.coco_metric import CocoMetric
from mmpose.models.backbones.hrnet import HRNet
from mmpose.models.data_preprocessors.data_preprocessor import \
    PoseDataPreprocessor
from mmpose.models.heads.heatmap_heads.cid_head import CIDHead
from mmpose.models.losses.classification_loss import InfoNCELoss
from mmpose.models.losses.heatmap_loss import FocalHeatmapLoss
from mmpose.models.necks.fmap_proc_neck import FeatureMapProcessor
from mmpose.models.pose_estimators.bottomup import BottomupPoseEstimator

# runtime
train_cfg.merge(dict(max_epochs=140, val_interval=10))

# optimizer
optim_wrapper = dict(optimizer=dict(
    type=Adam,
    lr=1e-3,
))

# learning policy
param_scheduler = [
    dict(
        type=MultiStepLR,
        begin=0,
        end=140,
        milestones=[90, 120],
        gamma=0.1,
        by_epoch=True)
]

# automatically scaling LR based on the actual training batch size
auto_scale_lr = dict(base_batch_size=160)

# hooks
default_hooks.merge(dict(checkpoint=dict(save_best='coco/AP', rule='greater')))

# codec settings
codec = dict(
    type=DecoupledHeatmap, input_size=(512, 512), heatmap_size=(128, 128))

# model settings
model = dict(
    type=BottomupPoseEstimator,
    data_preprocessor=dict(
        type=PoseDataPreprocessor,
        mean=[123.675, 116.28, 103.53],
        std=[58.395, 57.12, 57.375],
        bgr_to_rgb=True),
    backbone=dict(
        type=HRNet,
        in_channels=3,
        extra=dict(
            stage1=dict(
                num_modules=1,
                num_branches=1,
                block='BOTTLENECK',
                num_blocks=(4, ),
                num_channels=(64, )),
            stage2=dict(
                num_modules=1,
                num_branches=2,
                block='BASIC',
                num_blocks=(4, 4),
                num_channels=(48, 96)),
            stage3=dict(
                num_modules=4,
                num_branches=3,
                block='BASIC',
                num_blocks=(4, 4, 4),
                num_channels=(48, 96, 192)),
            stage4=dict(
                num_modules=3,
                num_branches=4,
                block='BASIC',
                num_blocks=(4, 4, 4, 4),
                num_channels=(48, 96, 192, 384),
                multiscale_output=True)),
        init_cfg=dict(
            type='Pretrained',
            checkpoint='https://download.openmmlab.com/mmpose/'
            'pretrain_models/hrnet_w48-8ef0771d.pth'),
    ),
    neck=dict(
        type=FeatureMapProcessor,
        concat=True,
    ),
    head=dict(
        type=CIDHead,
        in_channels=720,
        num_keypoints=17,
        gfd_channels=48,
        coupled_heatmap_loss=dict(type=FocalHeatmapLoss, loss_weight=1.0),
        decoupled_heatmap_loss=dict(type=FocalHeatmapLoss, loss_weight=4.0),
        contrastive_loss=dict(
            type=InfoNCELoss, temperature=0.05, loss_weight=1.0),
        decoder=codec,
    ),
    train_cfg=dict(max_train_instances=200),
    test_cfg=dict(
        multiscale_test=False,
        flip_test=True,
        shift_heatmap=False,
        align_corners=False))

# base dataset settings
dataset_type = 'CocoDataset'
data_mode = 'bottomup'
data_root = 'data/coco/'

# pipelines
train_pipeline = [
    dict(type=LoadImage),
    dict(type=BottomupRandomAffine, input_size=codec['input_size']),
    dict(type=RandomFlip, direction='horizontal'),
    dict(type=GenerateTarget, encoder=codec),
    dict(type=BottomupGetHeatmapMask),
    dict(type=PackPoseInputs),
]
val_pipeline = [
    dict(type=LoadImage),
    dict(
        type=BottomupResize,
        input_size=codec['input_size'],
        size_factor=64,
        resize_mode='expand'),
    dict(
        type=PackPoseInputs,
        meta_keys=('id', 'img_id', 'img_path', 'crowd_index', 'ori_shape',
                   'img_shape', 'input_size', 'input_center', 'input_scale',
                   'flip', 'flip_direction', 'flip_indices', 'raw_ann_info',
                   'skeleton_links'))
]

# data loaders
train_dataloader = dict(
    batch_size=20,
    num_workers=2,
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
    batch_size=1,
    num_workers=1,
    persistent_workers=True,
    drop_last=False,
    sampler=dict(type=DefaultSampler, shuffle=False, round_up=False),
    dataset=dict(
        type=CocoDataset,
        data_root=data_root,
        data_mode=data_mode,
        ann_file='annotations/person_keypoints_val2017.json',
        data_prefix=dict(img='val2017/'),
        test_mode=True,
        pipeline=val_pipeline,
    ))
test_dataloader = val_dataloader

# evaluators
val_evaluator = dict(
    type=CocoMetric,
    ann_file=data_root + 'annotations/person_keypoints_val2017.json',
    nms_thr=0.8,
    score_mode='keypoint',
)
test_evaluator = val_evaluator
