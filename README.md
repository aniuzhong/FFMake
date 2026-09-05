[🇨🇳](README-cn.md) | [🇺🇸](README.md)

[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)

# FFMake

> A reproducible exhaustive build system for FFmpeg.
> Targets Kylin V10 x86_64 by default; the build environment may adapts to my own workstation.
> Suggested workflow: build with the FFMake engine on a local high-performance Debian-based machine;
> per-machine environment drift can be resolved with agent assistance.
> GitHub-hosted builds are disabled due to cost.

# Do's and Don'ts

## Host

- Linux x86_64 Debian-based only; currently **Kylin V10**
- Other Linux distributions are not considered for now.
- Building on Windows is not considered.

## Toolchain

- Native Linux uses **GCC**.
- Windows cross-compilation uses **MinGW LLVM**.
- Native Windows **MSVC** is not supported.

## Target

- **x86_64-linux**
- **x86_64-windows**
