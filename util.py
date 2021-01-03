from __future__ import division
import torch
from torch.utils.serialization import load_lua
import torchvision.transforms as transforms
import numpy as np
import argparse
import time
import os
from PIL import Image
from modelsNIPS import decoder1,decoder2,decoder3,decoder4,decoder5
from modelsNIPS import encoder1,encoder2,encoder3,encoder4,encoder5
import torch.nn as nn



class WCT(nn.Module):
    def __init__(self,args):
        super(WCT, self).__init__()
        # load pre-trained network
        vgg1 = load_lua(args.vgg1,long_size=8)
        decoder1_torch = load_lua(args.decoder1,long_size=8)
        vgg2 = load_lua(args.vgg2,long_size=8)
        decoder2_torch = load_lua(args.decoder2,long_size=8)
        vgg3 = load_lua(args.vgg3,long_size=8)
        decoder3_torch = load_lua(args.decoder3,long_size=8)
        vgg4 = load_lua(args.vgg4,long_size=8)
        decoder4_torch = load_lua(args.decoder4,long_size=8)
        vgg5 = load_lua(args.vgg5,long_size=8)
        decoder5_torch = load_lua(args.decoder5,long_size=8)


        self.e1 = encoder1(vgg1)
        self.d1 = decoder1(decoder1_torch)
        self.e2 = encoder2(vgg2)
        self.d2 = decoder2(decoder2_torch)
        self.e3 = encoder3(vgg3)
        self.d3 = decoder3(decoder3_torch)
        self.e4 = encoder4(vgg4)
        self.d4 = decoder4(decoder4_torch)
        self.e5 = encoder5(vgg5)
        self.d5 = decoder5(decoder5_torch)

    def whiten_and_color(self,cF,sF):
        cFSize = cF.size()
        c_mean = torch.mean(cF,1) # c x (h x w)
        c_mean = c_mean.unsqueeze(1).expand_as(cF)
        cF = cF - c_mean

        contentConv = torch.mm(cF,cF.t()).div(cFSize[1]-1) + torch.eye(cFSize[0]).float()
        c_u,c_e,c_v = torch.svd(contentConv,some=False)

        k_c = cFSize[0]
        for i in range(cFSize[0]):
            if c_e[i] < 0.00001:
                k_c = i
                break

        sFSize = sF.size()
        s_mean = torch.mean(sF,1)
        sF = sF - s_mean.unsqueeze(1).expand_as(sF)
        styleConv = torch.mm(sF,sF.t()).div(sFSize[1]-1)
        s_u,s_e,s_v = torch.svd(styleConv,some=False)

        k_s = sFSize[0]
        for i in range(sFSize[0]):
            if s_e[i] < 0.00001:
                k_s = i
                break
        # -- deep feature perturbation
        # if add_noise == True:
        originalRandomNoise = torch.randn(k_s, k_s).float()
        n_u, n_e, n_v = torch.svd(originalRandomNoise)
        orthogonalNoise = n_u

        c_d = torch.sqrt(c_e[0:k_c]).pow(-1)
        s_d1 = torch.sqrt(s_e[0:k_s])

        # step1 = torch.mm(c_v[:,0:k_c],torch.diag(c_d))
        # step2 = torch.mm(step1,(c_v[:,0:k_c].t()))
        # whiten_cF = torch.mm(step2,cF)
        whiten_cF = torch.mm(torch.mm(torch.mm(c_v[:, 0:k_c],torch.diag(c_d)),torch.transpose(c_v[:, 0:k_c], 0, 1)),cF)
        perturbedFeature = torch.mm(torch.mm(torch.mm(torch.mm((s_v[:,0: k_s]),(torch.diag(s_d1))),orthogonalNoise),torch.transpose(s_v[:,0:k_s],0,1)) ,whiten_cF)
        originalFeature = torch.mm(torch.mm(torch.mm(s_v[:,0:k_s],torch.diag(s_d1)),torch.transpose(s_v[:,0:k_s],0,1)),whiten_cF)
        targetFeature = 0.2 * perturbedFeature + 0.8 * originalFeature

        # s_d = (s_e[0:k_s]).pow(0.5)
        # targetFeature = torch.mm(torch.mm(torch.mm(s_v[:,0:k_s],torch.diag(s_d)),(s_v[:,0:k_s].t())),whiten_cF)
        targetFeature = targetFeature + s_mean.unsqueeze(1).expand_as(targetFeature)
        return targetFeature

    def transform(self,cF,sF,csF,alpha):
        cF = cF.double()
        sF = sF.double()
        C,W,H = cF.size(0),cF.size(1),cF.size(2)
        _,W1,H1 = sF.size(0),sF.size(1),sF.size(2)
        cFView = cF.view(C,-1)
        sFView = sF.view(C,-1)

        targetFeature = self.whiten_and_color(cFView.float(),sFView.float())
        targetFeature = targetFeature.view_as(cF.float())
        ccsF = alpha* targetFeature.float() + (1.0 - alpha) * cF.float()
        ccsF = ccsF.float().unsqueeze(0)
        csF.data.resize_(ccsF.size()).copy_(ccsF)
        return csF
