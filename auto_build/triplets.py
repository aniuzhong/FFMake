"""Triplet table: target platform = arch + OS (vcpkg-triplet analog).

Each triplet drives:
  - autotools cross args (--host/--cross-prefix) injected by the makefile runner
  - FFmpeg cross flags (--enable-cross-compile/--target-os/...) in the loop
  - shared-library artifact expectations in validate.py
  - the per-triplet sysroot layout workspace/out/<triplet>/

Host tools (nasm etc.) are NOT per-triplet: they run on the build machine
and live in workspace/tools/bin (vcpkg's downloads/tools analog), shared
by every triplet via PATH.
"""

TRIPLETS = {
    # native build: no cross prefix, ELF shared libs
    "linux-x86_64": {
        "cross_prefix": "",
        "target_os": "linux",
        "shlib_dirs": ["lib"],
        "shlib_glob": "lib*.so*",
        "exe": "ffmpeg",
        "ffmpeg_flags": [],
    },
    # mingw-w64 cross: PE binaries; x264 et al. install run DLLs into bin/
    # and import libs into lib/, so both dirs are scanned.
    "mingw-x86_64": {
        "cross_prefix": "x86_64-w64-mingw32-",
        "target_os": "mingw32",
        "shlib_dirs": ["lib", "bin"],
        "shlib_glob": "*.dll",
        "exe": "ffmpeg.exe",
        "ffmpeg_flags": [
            "--enable-cross-compile",
            "--target-os=mingw32",
            "--cross-prefix=x86_64-w64-mingw32-",
            "--arch=x86_64",
        ],
    },
}

DEFAULT = "linux-x86_64"


def get(triplet):
    return TRIPLETS[triplet]
