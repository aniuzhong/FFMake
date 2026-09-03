# =============================================================================
# FFMake act-runner image —— a reusable test container aligned with the capability
# surface of GH-hosted ubuntu-24.04
#
# Build:   docker build -t ffmake-act-ubuntu:24.04 -f docker/act-ubuntu.Dockerfile docker/
# Probe:   gh act workflow_dispatch -W .github/workflows/act-release-test.yml \
#          -P ubuntu-latest=ffmake-act-ubuntu:24.04 --bind --pull=false
# Full run: same as above plus --input full=true --input triplet mingw-x86_64-llvm (takes hours)
# Cleanup: docker run --rm -v "$PWD":/w ubuntu:24.04 \
#          chown -R $(id -u):$(id -g) /w/workspace
#
# ── Practical knowledge (each bullet backed by hard‑earned lessons) ──────────
# 1. --pull=false is mandatory: act defaults to force‑pull every time; this image
#    is built locally and does not exist on Docker Hub, nor can registry mirrors
#    (domestic mirrors) find it – mirrors only proxy public images. Acceleration
#    for pulling public base images is handled via /etc/docker/daemon.json.
# 2. --bind is mandatory: act defaults to "copy mode", where writes inside the
#    container do not flow back to the host. Adding --bind makes workspace/
#    distfiles (117+ cached packages) and the stamps/out three‑layer hierarchy
#    share the same pool with the host – act and the host engine share the
#    same physical directory.
# 3. act 0.2.89 does not have a --user flag (the container always runs as root)
#    → build artefacts on the host end up owned by root. Use the "cleanup"
#    container above to chown them back (hido is in the docker group, so no sudo).
# 4. The mingw-x86_64-llvm target can be fully built inside this container:
#    wine 9.0 ships with built‑in implementations of msvcp140/vcruntime140,
#    so smoke tests do not require CrossOver‑style vcruntime files.
# 5. Linux‑target full builds can also be fully satisfied inside this container
#    without extra packages (the host‑provided layer is baked in by default,
#    see each RUN in "host‑provided layer" below; the mingw target does not
#    depend on that layer – the base image alone is self‑sufficient).
#
# ── Probe baseline (for reference, not a defect list) ─────────────────────────
# 【port list semantics】STATUS only recognises port artefacts (.pc) that are
#   placed into the DEFAULT triplet sysroot (via validate.is_installed).
#   system‑pc ports "borrow" the configure system‑directory fallback – they do
#   not land in sysroot and leave no stamp. As a result cairo/opengl will always
#   show as missing in the port list, even though they are actually enabled in
#   the final product (matrix ✅ comes from configuration) – this is by design,
#   not a bug.
# 【Expected missing】cairo / opengl (system‑pc borrows from host, as above);
#   fftw3 (not requested by flags, stateful). The host‑provided layer ensures
#   that configure’s system fallback has material to borrow, allowing the Linux
#   target to converge – it does not change the port list status.
# 【Expected missing pre‑installed items】opencv4(4.6) / OpenColorIO(2.1.3) are
#   installed but not in the port list (they are not ports and not requested by
#   flags), pre‑placed for future flag‑based turning green.
# 【Hit signals】117+ cached distfiles; built ports show as installed;
#   PKG_CONFIG_PATH/PATH point to workspace/out/linux-x86_64 (--bind mounts the
#   host path as‑is).
# 【Self‑check loop】if smbclient (which has a sysroot .pc + stamp) reappears as
#   missing, or a large number of installed entries turn red, the image layers
#   have been altered or the base upgraded – go back and review the two RUN
#   layers against this baseline.
# =============================================================================
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# ── Base layer: what the mingw target needs to be self‑sufficient (Debian‑style layout is a hard engine dependency) ────────────────────
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends \
      ca-certificates curl xz-utils unzip file \
      git patch make pkg-config \
      build-essential python3 \
      wine wine64 \
 && rm -rf /var/lib/apt/lists/*

# ── Host‑provided layer: system‑pc / host probing surface for Linux targets, plus pre‑installation of large "feedable" packages ──────
# This is the containerised expression of README principle #3: "if the host supports it, borrow it". The container acts as another host;
# installing packages here is the "feeding" step. After feeding, Linux‑target full builds can converge inside this container with zero
# additional packages.
#
# Cache‑friendly layer splitting (key constraint: Docker invalidates the entire chain from the first changed layer onward —
# "stable and large first, volatile and small last"; editing lower layers must not force re‑pulling of upper heavy layers;
# each layer cleans its own update/lists, and package groups do not interfere with each other):
#   L1 CUDA (~2GB, most stable) → L2 opencv/ocio pre‑install (~1GB, stable)
#   → L3 cairo/gl/smb/glib (medium, stable) → L4 vdpau/va/asound/v4l (small)
#   → L5 X11/xcb (small, most likely to gain packages during debugging)
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

# ── Build helper tools (exposed during cold builds for the first time; never triggered on hot reuse paths) ──────────────────────
# Lesson: gmp's configure strictly requires m4 ("No usable m4 in $PATH") – Kylin
# host has it by default, but the container base layer does not (build-essential
# does not include it). m4/bison/flex are classic autotools dependencies; place
# them in a separate small layer to avoid invalidating the base layer cache
# (touching it would force re‑pulling the 2GB feed layer).
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends m4 bison flex gettext \
      python3-dev \
 && rm -rf /var/lib/apt/lists/*

# ── pkg‑config implementation alignment (critical! separate small layer, so failures don't cascade into the big apt layers above) ──────────
# noble's /usr/bin/pkg-config is libpkgconf 1.8.1; vanilla 0.29.x also escapes
# non‑ASCII bytes in .pc files to \NN one by one (hex verified, independent of
# locale) – FFmpeg does not unescape, so any -I containing "repo" paths in .pc
# files (generated by third‑party build systems like lilv) gets corrupted.
# The real fix is the engine wrapper (workspace/tools/bin/pkg-config, python):
# it unescapes and replaces non‑ASCII real paths with ASCII aliases from
# pkgmap.json.
# This layer builds 0.29.2 merely to align the implementation version with the
# vanilla 0.29.x family (replacing 1.8.1; multiarch pc_path lesson below).
# Escaping issues are always handled by the wrapper – provided that the wrapper
# is not shadowed by a directory earlier in PATH (see the CUDA layer lesson).
# Lesson: deb.debian.org pool does not have the .orig.tar.xz for 0.29.2 (404),
# so use the official source tarball.
# Lesson2: vanilla 0.29.2 defaults to pc_path=/usr/lib/pkgconfig:/usr/share/pkgconfig,
# without multiarch – Debian‑derived libpkgconf and Kylin's 0.29.1 both carry
# distribution patches. Without multiarch, configure's --exists (which walks
# the full dependency graph) cannot find multiarch libraries like cairo,
# and an error‑driven loop will treat system‑pc ports as missing and try to
# build them – strict gatekeeping will definitely fail.
# Thus --with-pc-path must be explicitly set to mirror the distribution behaviour.
RUN curl -fsSL --retry 3 https://pkg-config.freedesktop.org/releases/pkg-config-0.29.2.tar.gz \
 | tar -xz -C /tmp && cd /tmp/pkg-config-0.29.2 \
 && ./configure --prefix=/usr --with-internal-glib \
      --with-pc-path="/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/lib/pkgconfig:/usr/share/pkgconfig" \
      -q > /dev/null \
 && make -j"$(nproc)" > /dev/null && make install > /dev/null \
 && cd / && rm -rf /tmp/pkg-config-0.29.2

# CUDA_HOME structure fix v2: real directory + precise symlinks (the entire‑tree /usr mirror approach is deprecated).
# Lesson (ultimate root cause of the lilv‑0 ghost): ln -sfn /usr /usr/local/cuda makes
# /usr/local/cuda/bin exactly equivalent to /usr/bin. The engine prepends CUDA bin to
# PATH (loop.cuda_bin does this to discover nvcc), and the bare pkg‑config there
# shadows the engine wrapper in tools/bin – the wrapper's "unescape + ASCII alias"
# logic is completely bypassed. Vanilla 0.29.2 then escapes non‑ASCII bytes in .pc
# files to \NN one by one (hex verified), breaking -I for all sysroot libraries such
# as lilv. System libraries (cairo etc.) use ASCII /usr paths and are unaffected,
# making the symptom "only lilv dies" extremely misleading.
# The real directory holds only nvcc + include/lib mirrors: CUDA bin does not contain
# pkg‑config, so the wrapper regains control. nvcc finds its companions (ptxas,
# cudafe++, etc.) through the real path /usr/bin (the previous cuda‑nvcc check
# passed under the /usr mirror, confirming this works).
RUN mkdir -p /usr/local/cuda/bin \
 && ln -sfn /usr/include /usr/local/cuda/include \
 && ln -sfn /usr/lib/x86_64-linux-gnu /usr/local/cuda/lib \
 && ln -sfn /usr/lib/x86_64-linux-gnu /usr/local/cuda/lib64 \
 && ln -sfn /usr/bin/nvcc /usr/local/cuda/bin/nvcc
ENV CUDA_HOME=/usr/local/cuda
# CUDA: flag‑driven host requirement (linux flags include --enable-cuda-nvcc). The engine looks for nvcc via CUDA_HOME
# (default /usr/local/cuda), but apt installs it to /usr/bin – the precise symlinks above complete the CUDA_HOME
# structure (include → cuda.h, lib → multiarch libcudart).
# Verified version (noble repo): CUDA 12.0 (Ubuntu repack has relaxed version checks for the distro's gcc).
# Verified version (noble repo): opencv 4.6.0 (the C‑mode #error from focal 4.2 disappears here
#   – conditions for libopencv B‑category turning green are now ready) / opencolorio 2.1.3 (v2 C++ API ✓) /
#   libtorch-dev is missing in noble (torch stays on the official pre‑compiled zip approach).
# Note: opencv/opencolorio are not in linux flags – installing them is just pre‑placement;
#   they will only enter configuration and be counted in the matrix when flags request them.

# ── Three wine pitfalls (specific to Ubuntu noble repack) ────────────────────────────────
# Pitfall 1: wine64 is a bare loader package; it does NOT provide /usr/bin/wine64.
#            The real binary is at /usr/lib/wine/wine64.
# Pitfall 2: The `wine` metapackage's /usr/bin/wine wrapper unconditionally probes for wine32
#            ("it looks like wine32 is missing") – same disease as Kylin wine 5.0.
#            Installing i386 multiarch would fix it but blows up the image size – not worth it.
# Pitfall 3: The loader cannot be invoked via a symlink – it resolves runtime libraries
#            based on its own real path; a symlink makes it fail to find peer files
#            ("could not exec the wine loader"). An exec wrapper script must be used,
#            preserving the loader's real path.
# wineserver does not have this path‑resolution issue; a symlink works fine.
RUN printf '#!/bin/sh\nexec /usr/lib/wine/wine64 "$@"\n' > /usr/local/bin/wine \
 && chmod +x /usr/local/bin/wine \
 && ln -s /usr/lib/wine/wineserver /usr/local/bin/wineserver

# ── node20: act runs JS actions (actions/checkout@v4 requires node20+) ──────────────
RUN curl -fsSL https://nodejs.org/dist/v20.18.1/node-v20.18.1-linux-x64.tar.xz \
 | tar -xJ -C /usr/local --strip-components=1

# ── git: under --bind mode, the container directly operates on the host‑owned repository; unified trust ─────────────────
# Also: slow‑speed abort + HTTP/1.1 + global proxy. Lesson 1: git clone libjxl connecting directly to GitHub
# would hang during transfer (0 bytes in 10 minutes) – git has no low‑speed timeout by default, and _run_net's
# proxy fallback only triggers on "failure", so hanging bypasses it. Lesson 2: libjxl's submodule skcms is hosted
# on skia.googlesource.com (Google‑owned, unreachable directly), and the submodule step is a bare self.run
# without proxy fallback – hence we configure git globally to use xray (container network=host,
# 127.0.0.1:10808 is the host proxy), covering clone/checkout/submodule all at once with a single setting.
RUN git config --system safe.directory '*' \
 && git config --system http.lowSpeedLimit 1000 \
 && git config --system http.lowSpeedTime 30 \
 && git config --system http.version HTTP/1.1 \
 && git config --system http.proxy http://127.0.0.1:10808

# ── Rust toolchain: dedicated for librav1e (rav1e AV1 encoder, a Rust project) ────────────────
# Lesson: librav1e's steps hardcode $HOME/.cargo/bin/{cargo,cbindgen} – the host has
# rustup, but the container does not (act runs as root, HOME=/root, matching the recipe path).
# rustup minimal installs only rustc+cargo+std; cbindgen is installed via cargo install
# to the same directory.
# Both network steps and cargo's crates.io fetching go through xray (to prevent direct‑connect
# hangs, a recurring issue).
# Side‑effects checked: config.toml's proxy only affects cargo, and does not pollute localhost
# services.
RUN https_proxy=http://127.0.0.1:10808 http_proxy=http://127.0.0.1:10808 \
    curl -fsSL --retry 3 https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain stable \
      --target x86_64-pc-windows-gnu \
 && printf '[http]\nproxy = "http://127.0.0.1:10808"\n' > /root/.cargo/config.toml \
 && https_proxy=http://127.0.0.1:10808 http_proxy=http://127.0.0.1:10808 \
    /root/.cargo/bin/cargo install --quiet cbindgen

# Note: workspace is always mounted at runtime (--bind), never baked into the image —
# the reuse value of distfiles/stamps/out lies entirely in cross-run persistence.
CMD ["/bin/bash"]
