[🇨🇳](README-cn.md) | [🇺🇸](README.md)

[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)

# FFMake

> 可复现的 FFmpeg 穷举式构建系统。
> 默认构建适配我正在使用的 Kylin V10 x86_64，该分支可能会随个人工作环境变更而归档；
> CI 中另含 Ubuntu latest 镜像作为发布。

# Do's and Don'ts (什么做而什么不做) 

## 宿主 (Host)

- 构建宿主机只用 **Linux x86_64 Debian 系**
    - 主分支跟 **Kylin V10**
    - CI 发布校验用 **Ubuntu Latest** 镜像
- 暂时不考虑在其它 Linux 发行版上构建
- 不考虑在 Windows 上构建

## 工具链 (Toolchain)

- Linux 原生用 **GCC** 
- Windows 交叉用 **MinGW LLWM**。
- **MinGW GCC** 暂时不用，已冻结。
- Windows 原生 **MSVC** 不支持。

## 目标 (Target) 

- **x86_64-linux**
- **x86_64-windows**

## 应对重型依赖的策略

针对 OpenCV、ONNX Runtime、TensorFlow 等重量级第三方库，我们不主动承接构建：

1. 复用 Debian/Ubuntu 官方维护的二进制包；
2. 评估官方发布的预编译二进制的可用性；