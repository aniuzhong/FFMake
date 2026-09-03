# =============================================================================
# FFMake CI image — capability surface aligned with GH-hosted ubuntu-24.04
#
# Stages:
#   base — pure build environment: apt feed layers, cross toolchain support,
#          wine, rust. Nothing act-specific.
#   ci   — base + act execution needs (node20 for JS actions, git trust/proxy).
#          This is the default target; tag it as the runner image.
#
# Build:   docker build -t ffmake-act-ubuntu:24.04 -f docker/Dockerfile docker/
#          (re-tag freely; the image name is a local convention)
#
# XRAY_PROXY: OPTIONAL build-time proxy (apt mirrors fetched directly;
# rustup/cargo/git honor it when set). GitHub builds need no proxy — leave it
# empty. Local builds behind a host proxy pass:
#   --build-arg XRAY_PROXY=http://127.0.0.1:10808
# (scripts/build-image.sh does this). When set, git's global http.proxy and
# cargo's config.toml are also configured with it — both are CI-execution
# concerns (the act container shares the host network namespace).
#
# workspace is ALWAYS runtime-mounted (--bind), never baked in: the reuse
# value of distfiles/stamps/out lies entirely in cross-run persistence.
# =============================================================================

ARG XRAY_PROXY=

# ── stage: base ──────────────────────────────────────────────────────────────
FROM ubuntu:24.04 AS base
ARG XRAY_PROXY
ENV DEBIAN_FRONTEND=noninteractive

# ── Base layer: what the mingw target needs to be self-sufficient (Debian-style layout is a hard engine dependency)
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends \
      ca-certificates curl xz-utils unzip file \
      git patch make pkg-config \
      build-essential python3 \
      wine wine64 \
 && rm -rf /var/lib/apt/lists/*

# ── Host-provided layer: system-pc / host probing surface for Linux targets, plus pre-installation of large "feedable" packages
# Containerised expression of README principle #3: "if the host supports it, borrow it".
# Cache-friendly layer splitting: "stable and large first, volatile and small last".
#   L1 CUDA (~2GB) → L2 opencv/ocio → L3 cairo/gl/smb/glib → L4 vdpau/va/asound/v4l
#   → L5 X11/xcb (most likely to gain packages during debugging)
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends \
      nvidia-cuda-toolkit \
 && rm -rf /var/lib/apt/lists/*
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends \
      libopencv-dev libopencolorio-dev \
 && rm -rf /var/lib/apt/lists/*
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends \
      libcairo2-dev libgl-dev libsmbclient-dev \
      libglib2.0-dev \
 && rm -rf /var/lib/apt/lists/*
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends \
      libvdpau-dev libva-dev libasound2-dev libv4l-dev \
      libpulse-dev \
 && rm -rf /var/lib/apt/lists/*
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends \
      libx11-dev libxext-dev libxfixes-dev libxcb1-dev \
      libxcb-render0-dev libxcb-shm0-dev libxrandr-dev \
 && rm -rf /var/lib/apt/lists/*

# ── Build helper tools (cold-build first-exposure; never hit on hot reuse paths)
# gmp's configure strictly requires m4; gettext supplies the gettext/iconv m4
# macros zvbi's autoreconf needs; python3-dev supplies python-3.12-embed for
# vapoursynth; patchelf relocates ELF rpaths at dist time. Kept in one small
# layer to protect the feed-layer cache above.
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends m4 bison flex gettext \
      python3-dev patchelf \
 && rm -rf /var/lib/apt/lists/*

# ── pkg-config implementation alignment (vanilla 0.29.x, multiarch pc_path)
# noble's libpkgconf 1.8.1 and vanilla 0.29.x both escape non-ASCII bytes in
# .pc output as \NN — FFmpeg does not unescape. The engine wrapper
# (workspace/tools/bin/pkg-config) handles unescaping + ASCII aliasing; this
# build only aligns the implementation (and restores multiarch pc_path so
# --exists can walk multiarch system libs like cairo).
RUN curl -fsSL --retry 3 https://pkg-config.freedesktop.org/releases/pkg-config-0.29.2.tar.gz \
 | tar -xz -C /tmp && cd /tmp/pkg-config-0.29.2 \
 && ./configure --prefix=/usr --with-internal-glib \
      --with-pc-path="/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/lib/pkgconfig:/usr/share/pkgconfig" \
      -q > /dev/null \
 && make -j"$(nproc)" > /dev/null && make install > /dev/null \
 && cd / && rm -rf /tmp/pkg-config-0.29.2

# ── CUDA_HOME structure: real dir + precise symlinks (never mirror /usr wholesale —
# a /usr mirror would put a bare pkg-config in the CUDA bin dir the engine
# prepends to PATH, shadowing the engine wrapper and breaking non-ASCII -I).
RUN mkdir -p /usr/local/cuda/bin \
 && ln -sfn /usr/include /usr/local/cuda/include \
 && ln -sfn /usr/lib/x86_64-linux-gnu /usr/local/cuda/lib \
 && ln -sfn /usr/lib/x86_64-linux-gnu /usr/local/cuda/lib64 \
 && ln -sfn /usr/bin/nvcc /usr/local/cuda/bin/nvcc
ENV CUDA_HOME=/usr/local/cuda

# ── wine: three noble-repack pitfalls → exec wrapper preserving the real
# loader path (a symlink breaks the loader's peer-file resolution).
RUN printf '#!/bin/sh\nexec /usr/lib/wine/wine64 "$@"\n' > /usr/local/bin/wine \
 && chmod +x /usr/local/bin/wine \
 && ln -s /usr/lib/wine/wineserver /usr/local/bin/wineserver

# ── Rust toolchain (librav1e): rustup minimal + both triplets' targets;
# cbindgen lands in the same ~/.cargo/bin the recipes reference.
ARG XRAY_PROXY
RUN if [ -n "${XRAY_PROXY}" ]; then \
      export https_proxy=${XRAY_PROXY} http_proxy=${XRAY_PROXY}; \
    fi \
 && curl -fsSL --retry 3 https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain stable \
      --target x86_64-pc-windows-gnu \
 && if [ -n "${XRAY_PROXY}" ]; then \
      printf '[http]\nproxy = "%s"\n' "${XRAY_PROXY}" > /root/.cargo/config.toml; \
    fi \
 && if [ -n "${XRAY_PROXY}" ]; then \
      export https_proxy=${XRAY_PROXY} http_proxy=${XRAY_PROXY}; \
    fi \
 && /root/.cargo/bin/cargo install --quiet cbindgen

# ── stage: ci ────────────────────────────────────────────────────────────────
# Everything here exists only because the executor is act running JS actions
# and writing into a host-owned bind mount. Swap the executor → replace this
# stage, not the whole image.
FROM base AS ci
ARG XRAY_PROXY

# node20: actions/checkout@v4 requires node20+
RUN curl -fsSL https://nodejs.org/dist/v20.18.1/node-v20.18.1-linux-x64.tar.xz \
 | tar -xJ -C /usr/local --strip-components=1

# git: under --bind the container writes into a host-owned repo — trust it.
# Slow-speed abort + HTTP/1.1 cover direct GitHub transfers (libjxl lesson);
# the global proxy is set only when XRAY_PROXY was provided at build time.
RUN git config --system safe.directory '*' \
 && git config --system http.lowSpeedLimit 1000 \
 && git config --system http.lowSpeedTime 30 \
 && git config --system http.version HTTP/1.1 \
 && if [ -n "${XRAY_PROXY}" ]; then \
      git config --system http.proxy http://${XRAY_PROXY}; \
    fi

CMD ["/bin/bash"]
