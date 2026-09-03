[🇨🇳](README-cn.md) | [🇺🇸](README.md)

[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)

# FFMake

> A reproducible exhaustive build system for FFmpeg.
> By default, it targets Kylin V10 x86_64, which I am currently using; This branch may be archived as my personal working environment changes.
> The CI also includes an Ubuntu latest image for releases.

# Do's and Don'ts

## Host

- The build host is **Linux x86_64 Debian-based** only.
    - Main branch tracks **Kylin V10**.
    - CI release validation uses **Ubuntu Latest** image.
- Other Linux distributions are not considered for now.
- Building on Windows are not considered.

## Toolchain

- Native Linux uses **GCC**.
- Windows cross‑compilation uses **MinGW LLVM**.
- **MinGW GCC** is frozen and not used for now.
- Native Windows **MSVC** is not supported.

## Target

- **x86_64-linux**
- **x86_64-windows**

## Strategy for Heavy Dependencies

For heavyweight third‑party libraries such as OpenCV, ONNX Runtime, and TensorFlow, we do not actively take on their builds:

1. Evaluate the availability of official pre‑compiled binaries.
2. Reuse the binary packages maintained officially by Debian/Ubuntu;