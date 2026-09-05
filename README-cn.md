[🇨🇳](README-cn.md) | [🇺🇸](README.md)

[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)

# FFMake

> 可复现的 FFmpeg 穷举式构建系统。
> 默认适配 Kylin V10 x86_64，构建环境可能会根据我的个人工作机调整。
> 建议开发者使用 FFMake 引擎在本地高性能 Debian 系机器上进行构建；各机器间的环境差异可由 Agent 辅助消解。
> GitHub 托管构建由于成本原因暂不启用。

# 什么做而什么不做

## 宿主

- 构建宿主机只用 **Linux x86_64 Debian 系**，目前为 **Kylin V10**
- 暂时不考虑在其它 Linux 发行版上构建
- 不考虑在 Windows 上构建

## 工具链

- Linux 原生用 **GCC**
- Windows 交叉用 **MinGW LLVM**
- Windows 原生 **MSVC** 不支持

## 目标

- **x86_64-linux**
- **x86_64-windows**
