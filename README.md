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

## Kylin V10 x86_64 Full Feature Comparison

- Total options (features/external libs): 136 | Enabled: 111 | Disabled: 25
- Disabled 25 = mutually exclusive groups yielding 12 + platform unsupported 9 + development/diagnostic 5 - cross 1, plus 3 aliases (actually enabled)

| configure option | Status | Description |
|---|---|---|
| ── TLS backend (n choose 1, selected openssl) |  | Four choose one: openssl enabled |
| --enable-openssl | ✓ Enabled |  |
| --enable-gnutls | ✗ Disabled | Mutually exclusive: openssl selected |
| --enable-mbedtls | ✗ Disabled | Mutually exclusive: openssl selected |
| --enable-libtls | ✗ Disabled | Mutually exclusive: openssl selected |
| --enable-gcrypt | ✗ Disabled | Mutually exclusive: openssl selected |
| ── EVC decoder (n choose 1, selected libxevd) |  | Two profiles of the same decoder, configure forbids enabling both |
| --enable-libxevd | ✓ Enabled |  |
| --enable-libxevdb | ✗ Disabled | Mutually exclusive: libxevd selected |
| ── EVC encoder (n choose 1, selected libxeve) |  | Same as above (encoder pair) |
| --enable-libxeve | ✓ Enabled |  |
| --enable-libxeveb | ✗ Disabled | Mutually exclusive: libxeve selected |
| ── Vulkan GLSL frontend (n choose 1, selected libshaderc) |  | Two shader frontends for Vulkan filters, configure forbids enabling both |
| --enable-libshaderc | ✓ Enabled |  |
| --enable-libglslang | ✗ Disabled | Mutually exclusive: libshaderc selected |
| ── Intel Media SDK generation (selected new libvpl) |  | Old and new generations overlap in functionality, vpl chosen |
| --enable-libvpl | ✓ Enabled |  |
| --enable-libmfx | ✗ Disabled | Mutually exclusive: libvpl selected |
| ── XAVS generation (selected new xavs2) |  | Old project deprecated, xavs2 chosen |
| --enable-libxavs2 | ✓ Enabled |  |
| --enable-libxavs | ✗ Disabled | Mutually exclusive: libxavs2 selected |
| --enable-jni | ✗ Disabled | Platform unsupported |
| --enable-linux-perf | ✗ Disabled | Platform unsupported |
| --enable-macos-kperf | ✗ Disabled | Platform unsupported |
| --enable-mediacodec | ✗ Disabled | Platform unsupported |
| --enable-mediafoundation | ✗ Disabled | Platform unsupported |
| --enable-mmal | ✗ Disabled | Platform unsupported |
| --enable-ohcodec | ✗ Disabled | Platform unsupported |
| --enable-rkmpp | ✗ Disabled | Platform unsupported |
| ── Development/diagnostic switches (non‑functional) |  |  |
| --enable-extra-warnings | ✗ Disabled | Development/diagnostic only, not enabled in release builds |
| --enable-memory-poisoning | ✗ Disabled | Development/diagnostic only, not enabled in release builds |
| --enable-neon-clobber-test | ✗ Disabled | Development/diagnostic only, not enabled in release builds |
| --enable-ossfuzz | ✗ Disabled | Development/diagnostic only, not enabled in release builds |
| --enable-xmm-clobber-test | ✗ Disabled | Development/diagnostic only, not enabled in release builds |
| ── Aliases (functionally already enabled) |  |  |
| --enable-libfontconfig | ✓ Enabled (alias) | Enabled via --enable-fontconfig |
| --enable-liblcevc-dec | ✓ Enabled (alias) | Enabled via --enable-liblcevc_dec |
| --enable-sdl | ✓ Enabled (alias) | Enabled via --enable-sdl2 |
| ── Standalone external libraries (all enabled) |  |  |
| --enable-avisynth | ✓ Enabled |  |
| --enable-cairo | ✓ Enabled |  |
| --enable-chromaprint | ✓ Enabled |  |
| --enable-cuda-nvcc | ✓ Enabled |  |
| --enable-decklink | ✓ Enabled |  |
| --enable-frei0r | ✓ Enabled |  |
| --enable-gmp | ✓ Enabled |  |
| --enable-ladspa | ✓ Enabled |  |
| --enable-lcms2 | ✓ Enabled |  |
| --enable-libaom | ✓ Enabled |  |
| --enable-libaribb24 | ✓ Enabled |  |
| --enable-libaribcaption | ✓ Enabled |  |
| --enable-libass | ✓ Enabled |  |
| --enable-libbluray | ✓ Enabled |  |
| --enable-libbs2b | ✓ Enabled |  |
| --enable-libcaca | ✓ Enabled |  |
| --enable-libcdio | ✓ Enabled |  |
| --enable-libcodec2 | ✓ Enabled |  |
| --enable-libdav1d | ✓ Enabled |  |
| --enable-libdavs2 | ✓ Enabled |  |
| --enable-libdc1394 | ✓ Enabled |  |
| --enable-libdvdnav | ✓ Enabled |  |
| --enable-libdvdread | ✓ Enabled |  |
| --enable-libfdk-aac | ✓ Enabled |  |
| --enable-libflite | ✓ Enabled |  |
| --enable-libfreetype | ✓ Enabled |  |
| --enable-libfribidi | ✓ Enabled |  |
| --enable-libgme | ✓ Enabled |  |
| --enable-libgsm | ✓ Enabled |  |
| --enable-libharfbuzz | ✓ Enabled |  |
| --enable-libiec61883 | ✓ Enabled |  |
| --enable-libilbc | ✓ Enabled |  |
| --enable-libjack | ✓ Enabled |  |
| --enable-libjxl | ✓ Enabled |  |
| --enable-libklvanc | ✓ Enabled |  |
| --enable-libkvazaar | ✓ Enabled |  |
| --enable-liblc3 | ✓ Enabled |  |
| --enable-liblensfun | ✓ Enabled |  |
| --enable-libmodplug | ✓ Enabled |  |
| --enable-libmp3lame | ✓ Enabled |  |
| --enable-libmpeghdec | ✓ Enabled |  |
| --enable-libmysofa | ✓ Enabled |  |
| --enable-liboapv | ✓ Enabled |  |
| --enable-libonnxruntime | ✓ Enabled |  |
| --enable-libopencolorio | ✓ Enabled |  |
| --enable-libopencore-amrnb | ✓ Enabled |  |
| --enable-libopencore-amrwb | ✓ Enabled |  |
| --enable-libopencv | ✓ Enabled |  |
| --enable-libopenh264 | ✓ Enabled |  |
| --enable-libopenjpeg | ✓ Enabled |  |
| --enable-libopenmpt | ✓ Enabled |  |
| --enable-libopenvino | ✓ Enabled |  |
| --enable-libopus | ✓ Enabled |  |
| --enable-libplacebo | ✓ Enabled |  |
| --enable-libpulse | ✓ Enabled |  |
| --enable-libqrencode | ✓ Enabled |  |
| --enable-libquirc | ✓ Enabled |  |
| --enable-librabbitmq | ✓ Enabled |  |
| --enable-librav1e | ✓ Enabled |  |
| --enable-librist | ✓ Enabled |  |
| --enable-librsvg | ✓ Enabled |  |
| --enable-librtmp | ✓ Enabled |  |
| --enable-librubberband | ✓ Enabled |  |
| --enable-libshine | ✓ Enabled |  |
| --enable-libsmbclient | ✓ Enabled |  |
| --enable-libsnappy | ✓ Enabled |  |
| --enable-libsoxr | ✓ Enabled |  |
| --enable-libspeex | ✓ Enabled |  |
| --enable-libsrt | ✓ Enabled |  |
| --enable-libssh | ✓ Enabled |  |
| --enable-libsvtav1 | ✓ Enabled |  |
| --enable-libsvtjpegxs | ✓ Enabled |  |
| --enable-libtensorflow | ✓ Enabled |  |
| --enable-libtesseract | ✓ Enabled |  |
| --enable-libtheora | ✓ Enabled |  |
| --enable-libtorch | ✓ Enabled |  |
| --enable-libtwolame | ✓ Enabled |  |
| --enable-libuavs3d | ✓ Enabled |  |
| --enable-libv4l2 | ✓ Enabled |  |
| --enable-libvidstab | ✓ Enabled |  |
| --enable-libvmaf | ✓ Enabled |  |
| --enable-libvo-amrwbenc | ✓ Enabled |  |
| --enable-libvorbis | ✓ Enabled |  |
| --enable-libvpx | ✓ Enabled |  |
| --enable-libvvenc | ✓ Enabled |  |
| --enable-libwebp | ✓ Enabled |  |
| --enable-libx264 | ✓ Enabled |  |
| --enable-libx265 | ✓ Enabled |  |
| --enable-libxcb | ✓ Enabled |  |
| --enable-libxcb-shape | ✓ Enabled |  |
| --enable-libxcb-shm | ✓ Enabled |  |
| --enable-libxcb-xfixes | ✓ Enabled |  |
| --enable-libxml2 | ✓ Enabled |  |
| --enable-libxvid | ✓ Enabled |  |
| --enable-libzimg | ✓ Enabled |  |
| --enable-libzmq | ✓ Enabled |  |
| --enable-libzvbi | ✓ Enabled |  |
| --enable-lv2 | ✓ Enabled |  |
| --enable-openal | ✓ Enabled |  |
| --enable-opencl | ✓ Enabled |  |
| --enable-opengl | ✓ Enabled |  |
| --enable-pocketsphinx | ✓ Enabled |  |
| --enable-vapoursynth | ✓ Enabled |  |
| --enable-vulkan-static | ✓ Enabled |  |
| --enable-whisper | ✓ Enabled |  |