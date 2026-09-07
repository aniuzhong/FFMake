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

## Kylin V10 x86_64 全特性对照表

- 选项全集(功能/外部库):136 | 已启用:111 | 未启用:25
- 未启用 25 = 互斥组让位 12 + 平台不支持 9 + 开发诊断 5 - 交叉 1,另含别名 3(实际已启用)

| configure 参数 | 状态 | 说明 |
|---|---|---|
| ── TLS 后端(n 选一,已选 openssl) |  | 四选一:openssl 已启用 |
| --enable-openssl | ✓ 已启用 |  |
| --enable-gnutls | ✗ 未启用 | 互斥:已选 openssl |
| --enable-mbedtls | ✗ 未启用 | 互斥:已选 openssl |
| --enable-libtls | ✗ 未启用 | 互斥:已选 openssl |
| --enable-gcrypt | ✗ 未启用 | 互斥:已选 openssl |
| ── EVC 解码(n 选一,已选 libxevd) |  | 二选一:同一解码器的两个 profile,configure 禁止同启 |
| --enable-libxevd | ✓ 已启用 |  |
| --enable-libxevdb | ✗ 未启用 | 互斥:已选 libxevd |
| ── EVC 编码(n 选一,已选 libxeve) |  | 二选一:同上(编码器对) |
| --enable-libxeve | ✓ 已启用 |  |
| --enable-libxeveb | ✗ 未启用 | 互斥:已选 libxeve |
| ── Vulkan GLSL 前端(n 选一,已选 libshaderc) |  | 二选一:vulkan 滤镜的两个 shader 前端,configure 禁止同启 |
| --enable-libshaderc | ✓ 已启用 |  |
| --enable-libglslang | ✗ 未启用 | 互斥:已选 libshaderc |
| ── Intel 媒体 SDK 代际(已选新版 libvpl) |  | 新旧两代功能重叠,已取 vpl |
| --enable-libvpl | ✓ 已启用 |  |
| --enable-libmfx | ✗ 未启用 | 互斥:已选 libvpl |
| ── XAVS 代际(已取新版 xavs2) |  | 老项目已废弃,已取 xavs2 |
| --enable-libxavs2 | ✓ 已启用 |  |
| --enable-libxavs | ✗ 未启用 | 互斥:已选 libxavs2 |
| --enable-jni | ✗ 未启用 | 平台不支持 |
| --enable-linux-perf | ✗ 未启用 | 平台不支持 |
| --enable-macos-kperf | ✗ 未启用 | 平台不支持 |
| --enable-mediacodec | ✗ 未启用 | 平台不支持 |
| --enable-mediafoundation | ✗ 未启用 | 平台不支持 |
| --enable-mmal | ✗ 未启用 | 平台不支持 |
| --enable-ohcodec | ✗ 未启用 | 平台不支持 |
| --enable-rkmpp | ✗ 未启用 | 平台不支持 |
| ── 开发/诊断开关(非功能特性) |  |  |
| --enable-extra-warnings | ✗ 未启用 | 开发/诊断专用,发布构建不启用 |
| --enable-memory-poisoning | ✗ 未启用 | 开发/诊断专用,发布构建不启用 |
| --enable-neon-clobber-test | ✗ 未启用 | 开发/诊断专用,发布构建不启用 |
| --enable-ossfuzz | ✗ 未启用 | 开发/诊断专用,发布构建不启用 |
| --enable-xmm-clobber-test | ✗ 未启用 | 开发/诊断专用,发布构建不启用 |
| ── 别名(功能实际已启用) |  |  |
| --enable-libfontconfig | ✓ 已启用(别名) | 以 --enable-fontconfig 形式启用 |
| --enable-liblcevc-dec | ✓ 已启用(别名) | 以 --enable-liblcevc_dec 形式启用 |
| --enable-sdl | ✓ 已启用(别名) | 以 --enable-sdl2 形式启用 |
| ── 单体外部库(全部已启用) |  |  |
| --enable-avisynth | ✓ 已启用 |  |
| --enable-cairo | ✓ 已启用 |  |
| --enable-chromaprint | ✓ 已启用 |  |
| --enable-cuda-nvcc | ✓ 已启用 |  |
| --enable-decklink | ✓ 已启用 |  |
| --enable-frei0r | ✓ 已启用 |  |
| --enable-gmp | ✓ 已启用 |  |
| --enable-ladspa | ✓ 已启用 |  |
| --enable-lcms2 | ✓ 已启用 |  |
| --enable-libaom | ✓ 已启用 |  |
| --enable-libaribb24 | ✓ 已启用 |  |
| --enable-libaribcaption | ✓ 已启用 |  |
| --enable-libass | ✓ 已启用 |  |
| --enable-libbluray | ✓ 已启用 |  |
| --enable-libbs2b | ✓ 已启用 |  |
| --enable-libcaca | ✓ 已启用 |  |
| --enable-libcdio | ✓ 已启用 |  |
| --enable-libcodec2 | ✓ 已启用 |  |
| --enable-libdav1d | ✓ 已启用 |  |
| --enable-libdavs2 | ✓ 已启用 |  |
| --enable-libdc1394 | ✓ 已启用 |  |
| --enable-libdvdnav | ✓ 已启用 |  |
| --enable-libdvdread | ✓ 已启用 |  |
| --enable-libfdk-aac | ✓ 已启用 |  |
| --enable-libflite | ✓ 已启用 |  |
| --enable-libfreetype | ✓ 已启用 |  |
| --enable-libfribidi | ✓ 已启用 |  |
| --enable-libgme | ✓ 已启用 |  |
| --enable-libgsm | ✓ 已启用 |  |
| --enable-libharfbuzz | ✓ 已启用 |  |
| --enable-libiec61883 | ✓ 已启用 |  |
| --enable-libilbc | ✓ 已启用 |  |
| --enable-libjack | ✓ 已启用 |  |
| --enable-libjxl | ✓ 已启用 |  |
| --enable-libklvanc | ✓ 已启用 |  |
| --enable-libkvazaar | ✓ 已启用 |  |
| --enable-liblc3 | ✓ 已启用 |  |
| --enable-liblensfun | ✓ 已启用 |  |
| --enable-libmodplug | ✓ 已启用 |  |
| --enable-libmp3lame | ✓ 已启用 |  |
| --enable-libmpeghdec | ✓ 已启用 |  |
| --enable-libmysofa | ✓ 已启用 |  |
| --enable-liboapv | ✓ 已启用 |  |
| --enable-libonnxruntime | ✓ 已启用 |  |
| --enable-libopencolorio | ✓ 已启用 |  |
| --enable-libopencore-amrnb | ✓ 已启用 |  |
| --enable-libopencore-amrwb | ✓ 已启用 |  |
| --enable-libopencv | ✓ 已启用 |  |
| --enable-libopenh264 | ✓ 已启用 |  |
| --enable-libopenjpeg | ✓ 已启用 |  |
| --enable-libopenmpt | ✓ 已启用 |  |
| --enable-libopenvino | ✓ 已启用 |  |
| --enable-libopus | ✓ 已启用 |  |
| --enable-libplacebo | ✓ 已启用 |  |
| --enable-libpulse | ✓ 已启用 |  |
| --enable-libqrencode | ✓ 已启用 |  |
| --enable-libquirc | ✓ 已启用 |  |
| --enable-librabbitmq | ✓ 已启用 |  |
| --enable-librav1e | ✓ 已启用 |  |
| --enable-librist | ✓ 已启用 |  |
| --enable-librsvg | ✓ 已启用 |  |
| --enable-librtmp | ✓ 已启用 |  |
| --enable-librubberband | ✓ 已启用 |  |
| --enable-libshine | ✓ 已启用 |  |
| --enable-libsmbclient | ✓ 已启用 |  |
| --enable-libsnappy | ✓ 已启用 |  |
| --enable-libsoxr | ✓ 已启用 |  |
| --enable-libspeex | ✓ 已启用 |  |
| --enable-libsrt | ✓ 已启用 |  |
| --enable-libssh | ✓ 已启用 |  |
| --enable-libsvtav1 | ✓ 已启用 |  |
| --enable-libsvtjpegxs | ✓ 已启用 |  |
| --enable-libtensorflow | ✓ 已启用 |  |
| --enable-libtesseract | ✓ 已启用 |  |
| --enable-libtheora | ✓ 已启用 |  |
| --enable-libtorch | ✓ 已启用 |  |
| --enable-libtwolame | ✓ 已启用 |  |
| --enable-libuavs3d | ✓ 已启用 |  |
| --enable-libv4l2 | ✓ 已启用 |  |
| --enable-libvidstab | ✓ 已启用 |  |
| --enable-libvmaf | ✓ 已启用 |  |
| --enable-libvo-amrwbenc | ✓ 已启用 |  |
| --enable-libvorbis | ✓ 已启用 |  |
| --enable-libvpx | ✓ 已启用 |  |
| --enable-libvvenc | ✓ 已启用 |  |
| --enable-libwebp | ✓ 已启用 |  |
| --enable-libx264 | ✓ 已启用 |  |
| --enable-libx265 | ✓ 已启用 |  |
| --enable-libxcb | ✓ 已启用 |  |
| --enable-libxcb-shape | ✓ 已启用 |  |
| --enable-libxcb-shm | ✓ 已启用 |  |
| --enable-libxcb-xfixes | ✓ 已启用 |  |
| --enable-libxml2 | ✓ 已启用 |  |
| --enable-libxvid | ✓ 已启用 |  |
| --enable-libzimg | ✓ 已启用 |  |
| --enable-libzmq | ✓ 已启用 |  |
| --enable-libzvbi | ✓ 已启用 |  |
| --enable-lv2 | ✓ 已启用 |  |
| --enable-openal | ✓ 已启用 |  |
| --enable-opencl | ✓ 已启用 |  |
| --enable-opengl | ✓ 已启用 |  |
| --enable-pocketsphinx | ✓ 已启用 |  |
| --enable-vapoursynth | ✓ 已启用 |  |
| --enable-vulkan-static | ✓ 已启用 |  |
| --enable-whisper | ✓ 已启用 |  |
