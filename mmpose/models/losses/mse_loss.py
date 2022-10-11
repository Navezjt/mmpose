# Copyright (c) OpenMMLab. All rights reserved.
import torch
import torch.nn as nn
from torch import Tensor

from mmpose.models.losses import GIoULoss
from mmpose.registry import MODELS


@MODELS.register_module()
class KeypointMSELoss(nn.Module):
    """MSE loss for heatmaps.

    Args:
        use_target_weight (bool): Option to use weighted MSE loss.
            Different joint types may have different target weights.
            Defaults to ``False``
        loss_weight (float): Weight of the loss. Defaults to 1.0
    """

    def __init__(self,
                 use_target_weight: bool = False,
                 loss_weight: float = 1.):
        super().__init__()
        self.criterion = nn.MSELoss()
        self.use_target_weight = use_target_weight
        self.loss_weight = loss_weight

    def forward(self, output: Tensor, target: Tensor,
                target_weights: Tensor) -> Tensor:
        """Forward function of loss.

        Note:
            - batch_size: B
            - num_keypoints: K
            - heatmaps height: H
            - heatmaps weight: W

        Args:
            output (Tensor): The output heatmaps with shape [B, K, H, W].
            target (Tensor): The target heatmaps with shape [B, K, H, W].
            target_weights (Tensor): The target weights of differet keypoints,
                with shape [B, K].

        Returns:
            Tensor: The calculated loss.
        """
        if self.use_target_weight:
            assert target_weights is not None
            assert output.ndim >= target_weights.ndim

            for i in range(output.ndim - target_weights.ndim):
                target_weights = target_weights.unsqueeze(-1)

            loss = self.criterion(output * target_weights,
                                  target * target_weights)
        else:
            loss = self.criterion(output, target)

        return loss * self.loss_weight


@MODELS.register_module()
class CombinedTargetMSELoss(nn.Module):
    """MSE loss for combined target.

    CombinedTarget: The combination of classification target
    (response map) and regression target (offset map).
    Paper ref: Huang et al. The Devil is in the Details: Delving into
    Unbiased Data Processing for Human Pose Estimation (CVPR 2020).

    Args:
        use_target_weight (bool): Option to use weighted MSE loss.
            Different joint types may have different target weights.
            Defaults to ``False``
        loss_weight (float): Weight of the loss. Defaults to 1.0
    """

    def __init__(self,
                 use_target_weight: bool = False,
                 loss_weight: float = 1.):
        super().__init__()
        self.criterion = nn.MSELoss(reduction='mean')
        self.use_target_weight = use_target_weight
        self.loss_weight = loss_weight

    def forward(self, output: Tensor, target: Tensor,
                target_weights: Tensor) -> Tensor:
        """Forward function of loss.

        Note:
            - batch_size: B
            - num_channels: C
            - heatmaps height: H
            - heatmaps weight: W
            - num_keypoints: K
            Here, C = 3 * K

        Args:
            output (Tensor): The output feature maps with shape [B, C, H, W].
            target (Tensor): The target feature maps with shape [B, C, H, W].
            target_weights (Tensor): The target weights of differet keypoints,
                with shape [B, K].

        Returns:
            Tensor: The calculated loss.
        """
        batch_size = output.size(0)
        num_channels = output.size(1)
        heatmaps_pred = output.reshape(
            (batch_size, num_channels, -1)).split(1, 1)
        heatmaps_gt = target.reshape(
            (batch_size, num_channels, -1)).split(1, 1)
        loss = 0.
        num_joints = num_channels // 3
        for idx in range(num_joints):
            heatmap_pred = heatmaps_pred[idx * 3].squeeze()
            heatmap_gt = heatmaps_gt[idx * 3].squeeze()
            offset_x_pred = heatmaps_pred[idx * 3 + 1].squeeze()
            offset_x_gt = heatmaps_gt[idx * 3 + 1].squeeze()
            offset_y_pred = heatmaps_pred[idx * 3 + 2].squeeze()
            offset_y_gt = heatmaps_gt[idx * 3 + 2].squeeze()
            if self.use_target_weight:
                target_weight = target_weights[:, idx, None]
                heatmap_pred = heatmap_pred * target_weight
                heatmap_gt = heatmap_gt * target_weight
            # classification loss
            loss += 0.5 * self.criterion(heatmap_pred, heatmap_gt)
            # regression loss
            loss += 0.5 * self.criterion(heatmap_gt * offset_x_pred,
                                         heatmap_gt * offset_x_gt)
            loss += 0.5 * self.criterion(heatmap_gt * offset_y_pred,
                                         heatmap_gt * offset_y_gt)
        return loss / num_joints * self.loss_weight


@MODELS.register_module()
class KeypointOHKMMSELoss(nn.Module):
    """MSE loss with online hard keypoint mining.

    Args:
        use_target_weight (bool): Option to use weighted MSE loss.
            Different joint types may have different target weights.
            Defaults to ``False``
        topk (int): Only top k joint losses are kept. Defaults to 8
        loss_weight (float): Weight of the loss. Defaults to 1.0
    """

    def __init__(self,
                 use_target_weight: bool = False,
                 topk: int = 8,
                 loss_weight: float = 1.):
        super().__init__()
        assert topk > 0
        self.criterion = nn.MSELoss(reduction='none')
        self.use_target_weight = use_target_weight
        self.topk = topk
        self.loss_weight = loss_weight

    def _ohkm(self, losses: Tensor) -> Tensor:
        """Online hard keypoint mining.

        Note:
            - batch_size: B
            - num_keypoints: K

        Args:
            loss (Tensor): The losses with shape [B, K]

        Returns:
            Tensor: The calculated loss.
        """
        ohkm_loss = 0.
        B = losses.shape[0]
        for i in range(B):
            sub_loss = losses[i]
            _, topk_idx = torch.topk(
                sub_loss, k=self.topk, dim=0, sorted=False)
            tmp_loss = torch.gather(sub_loss, 0, topk_idx)
            ohkm_loss += torch.sum(tmp_loss) / self.topk
        ohkm_loss /= B
        return ohkm_loss

    def forward(self, output: Tensor, target: Tensor,
                target_weights: Tensor) -> Tensor:
        """Forward function of loss.

        Note:
            - batch_size: B
            - num_keypoints: K
            - heatmaps height: H
            - heatmaps weight: W

        Args:
            output (Tensor): The output heatmaps with shape [B, K, H, W].
            target (Tensor): The target heatmaps with shape [B, K, H, W].
            target_weights (Tensor): The target weights of differet keypoints,
                with shape [B, K].

        Returns:
            Tensor: The calculated loss.
        """
        num_keypoints = output.size(1)
        if num_keypoints < self.topk:
            raise ValueError(f'topk ({self.topk}) should not be '
                             f'larger than num_keypoints ({num_keypoints}).')

        losses = []
        for idx in range(num_keypoints):
            if self.use_target_weight:
                target_weight = target_weights[:, idx, None, None]
                losses.append(
                    self.criterion(output[:, idx] * target_weight,
                                   target[:, idx] * target_weight))
            else:
                losses.append(self.criterion(output[:, idx], target[:, idx]))

        losses = [loss.mean(dim=(1, 2)).unsqueeze(dim=1) for loss in losses]
        losses = torch.cat(losses, dim=1)

        return self._ohkm(losses) * self.loss_weight


@MODELS.register_module()
class CombinedTargetIOULoss(nn.Module):
    """MSE loss for combined target.

    CombinedTarget: The combination of classification target
    (response map) and regression target (offset map).
    Paper ref: Huang et al. The Devil is in the Details: Delving into
    Unbiased Data Processing for Human Pose Estimation (CVPR 2020).

    Args:
        use_target_weight (bool): Option to use weighted MSE loss.
            Different joint types may have different target weights.
            Defaults to ``False``
        loss_weight (float): Weight of the loss. Defaults to 1.0
    """

    def __init__(self,
                 use_target_weight: bool = False,
                 loss_weight: float = 1.):
        super().__init__()
        self.criterion = nn.MSELoss(reduction='mean')
        self.iou_loss = GIoULoss()
        self.use_target_weight = use_target_weight
        self.loss_weight = loss_weight

    def forward(self, output: Tensor, target: Tensor,
                target_weights: Tensor) -> Tensor:
        """Forward function of loss.

        Note:
            - batch_size: B
            - num_channels: C
            - heatmaps height: H
            - heatmaps weight: W
            - num_keypoints: K
            Here, C = 3 * K

        Args:
            output (Tensor): The output feature maps with shape [B, C, H, W].
            target (Tensor): The target feature maps with shape [B, C, H, W].
            target_weights (Tensor): The target weights of differet keypoints,
                with shape [B, K].

        Returns:
            Tensor: The calculated loss.
        """
        W, H = output.shape[2:]
        batch_size = output.size(0)
        num_channels = output.size(1)
        heatmaps_pred = output.reshape(
            (batch_size, num_channels, -1)).split(1, 1)
        heatmaps_gt = target.reshape(
            (batch_size, num_channels, -1)).split(1, 1)
        loss = 0.
        num_joints = num_channels // 3
        for idx in range(num_joints):
            heatmap_pred = heatmaps_pred[idx * 3].squeeze()
            heatmap_gt = heatmaps_gt[idx * 3].squeeze()
            offset_x_pred = heatmaps_pred[idx * 3 + 1].squeeze()
            offset_x_gt = heatmaps_gt[idx * 3 + 1].squeeze()
            offset_y_pred = heatmaps_pred[idx * 3 + 2].squeeze()
            offset_y_gt = heatmaps_gt[idx * 3 + 2].squeeze()
            if self.use_target_weight:
                target_weight = target_weights[:, idx, None]
                heatmap_pred = heatmap_pred * target_weight
                heatmap_gt = heatmap_gt * target_weight
            # classification loss
            loss += 0.5 * self.criterion(heatmap_pred, heatmap_gt)

            bbox_gt = []
            bbox_pred = []
            for x in range(W):
                for y in range(H):
                    if heatmap_gt[:, x * H + y] == 0:
                        continue
                    x1 = torch.ones(batch_size) * x
                    y1 = torch.ones(batch_size) * y
                    gt_x2 = x1 + offset_x_gt[:, x * H + y]
                    gt_y2 = y1 + offset_y_gt[:, x * H + y]

                    mask_x = gt_x2 > x1
                    mask_y = gt_y2 > y1

                    t_bbox_gt = torch.stack(
                        [x1[mask_x], y1[mask_y], gt_x2[mask_x], gt_y2[mask_y]],
                        dim=-1)
                    bbox_gt.append(t_bbox_gt)
                    t_bbox_gt = torch.stack([
                        gt_x2[1 - mask_x], gt_y2[1 - mask_y], x1[1 - mask_x],
                        y1[1 - mask_y]
                    ],
                                            dim=-1)
                    bbox_gt.append(t_bbox_gt)

                    pred_x2 = x1 + offset_x_pred[:, x * H + y]
                    pred_y2 = y1 + offset_y_pred[:, x * H + y]

                    mask_x = pred_x2 > x1
                    mask_y = pred_y2 > y1

                    t_bbox_pred = torch.stack([
                        x1[mask_x], y1[mask_y], pred_x2[mask_x],
                        pred_y2[mask_y]
                    ],
                                              dim=-1)
                    bbox_pred.append(t_bbox_pred)

                    t_bbox_pred = torch.stack([
                        pred_x2[1 - mask_x], pred_y2[1 - mask_y],
                        x1[1 - mask_x], y1[1 - mask_y]
                    ],
                                              dim=-1)
                    bbox_pred.append(t_bbox_pred)

                    # B, 4
                    # t_bbox_gt = torch.stack([x1, y1, gt_x2, gt_y2], dim=-1)
                    # t_bbox_pred = torch.stack([x1, y1, pred_x2, pred_y2],
                    #                           dim=-1)
                    # bbox_gt.append(t_bbox_gt)
                    # bbox_pred.append(t_bbox_pred)
            bbox_gt = torch.cat(bbox_gt, dim=0).to(output.device)
            bbox_pred = torch.cat(bbox_pred, dim=0).to(output.device)
            loss += self.iou_loss(bbox_pred, bbox_gt)
            # regression loss
            # loss += 0.5 * self.criterion(heatmap_gt * offset_x_pred,
            #                              heatmap_gt * offset_x_gt)
            # loss += 0.5 * self.criterion(heatmap_gt * offset_y_pred,
            #                              heatmap_gt * offset_y_gt)
        return loss / num_joints * self.loss_weight
