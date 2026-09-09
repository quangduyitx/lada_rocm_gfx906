# SPDX-FileCopyrightText: Lada Authors
# SPDX-License-Identifier: AGPL-3.0

import math
import torch
import torch.nn as nn
from torch.nn import init as init
from torch.nn.modules.utils import _pair, _single
import torch.nn.functional as F
import torchvision.ops

def deform_conv2d_pure_pytorch(x, offset, weight, bias=None, stride=1, padding=0, dilation=1, mask=None):
    b, in_c, h, w = x.shape
    out_c, _, ks_h, ks_w = weight.shape
    K = ks_h * ks_w
    h_out = offset.shape[2]
    w_out = offset.shape[3]
    
    stride_h, stride_w = _pair(stride)
    pad_h, pad_w = _pair(padding)
    dil_h, dil_w = _pair(dilation)
    
    G = offset.shape[1] // (2 * K)
    c_per_g = in_c // G
    
    y_range = torch.arange(0, h_out, device=x.device, dtype=x.dtype) * stride_h
    x_range = torch.arange(0, w_out, device=x.device, dtype=x.dtype) * stride_w
    grid_y, grid_x = torch.meshgrid(y_range, x_range, indexing='ij')
    
    ky = torch.arange(0, ks_h, device=x.device, dtype=x.dtype) * dil_h
    kx = torch.arange(0, ks_w, device=x.device, dtype=x.dtype) * dil_w
    p_n_y, p_n_x = torch.meshgrid(ky, kx, indexing='ij')
    p_n_y = p_n_y.flatten().view(1, 1, K, 1, 1)
    p_n_x = p_n_x.flatten().view(1, 1, K, 1, 1)
    
    offset_reshaped = offset.view(b, G, K, 2, h_out, w_out)
    offset_y = offset_reshaped[:, :, :, 0, :, :]
    offset_x = offset_reshaped[:, :, :, 1, :, :]
    
    pos_y = grid_y.view(1, 1, 1, h_out, w_out) - pad_h + p_n_y + offset_y
    pos_x = grid_x.view(1, 1, 1, h_out, w_out) - pad_w + p_n_x + offset_x
    
    norm_x = (pos_x / (w - 1.0)) * 2.0 - 1.0
    norm_y = (pos_y / (h - 1.0)) * 2.0 - 1.0
    
    grid = torch.stack([norm_x, norm_y], dim=-1).view(b * G * K, h_out, w_out, 2)
    x_g = x.view(b, G, c_per_g, h, w).unsqueeze(2).expand(b, G, K, c_per_g, h, w).reshape(b * G * K, c_per_g, h, w)
    
    sampled = F.grid_sample(x_g, grid, mode='bilinear', padding_mode='zeros', align_corners=True)
    sampled = sampled.view(b, G, K, c_per_g, h_out, w_out)
    
    if mask is not None:
        mask_g = mask.view(b, G, K, 1, h_out, w_out)
        sampled = sampled * mask_g
        
    sampled = sampled.permute(0, 1, 3, 2, 4, 5).reshape(b, in_c * K, h_out, w_out)
    w_flat = weight.view(out_c, in_c * K, 1, 1)
    return F.conv2d(sampled, w_flat, bias=bias, stride=1)

def deform_conv2d_fallback(x, offset, weight, bias=None, stride=1, padding=0, dilation=1, mask=None):
    try:
        return torchvision.ops.deform_conv2d(x, offset, weight, bias, stride, padding, dilation, mask)
    except NotImplementedError:
        return deform_conv2d_pure_pytorch(x, offset, weight, bias, stride, padding, dilation, mask)

class ModulatedDeformConv2d(nn.Module):
    def __init__(self,
                 in_channels,
                 out_channels,
                 kernel_size,
                 stride=1,
                 padding=0,
                 dilation=1,
                 groups=1,
                 deform_groups=1,
                 bias=True):
        super(ModulatedDeformConv2d, self).__init__()

        self.in_channels = in_channels
        self.out_channels = out_channels
        self.kernel_size = _pair(kernel_size)
        self.stride = stride
        self.padding = padding
        self.dilation = dilation
        self.groups = groups
        self.deform_groups = deform_groups
        self.with_bias = bias
        # enable compatibility with nn.Conv2d
        self.transposed = False
        self.output_padding = _single(0)

        self.weight = nn.Parameter(torch.Tensor(out_channels, in_channels // groups, *self.kernel_size))
        if bias:
            self.bias = nn.Parameter(torch.Tensor(out_channels))
        else:
            self.register_parameter('bias', None)
        self.init_weights()

    def init_weights(self):
        n = self.in_channels
        for k in self.kernel_size:
            n *= k
        stdv = 1. / math.sqrt(n)
        self.weight.data.uniform_(-stdv, stdv)
        if self.bias is not None:
            self.bias.data.zero_()

        if hasattr(self, 'conv_offset'):
            self.conv_offset.weight.data.zero_()
            self.conv_offset.bias.data.zero_()

    def forward(self, x, offset, mask):
        return deform_conv2d_fallback(x, offset, self.weight, self.bias,
                                      self.stride, self.padding, self.dilation, mask)