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

    # mingw-w64 cross on the llvm-mingw toolchain (clang/lld, modern
    # mingw-w64 headers). Same target as mingw-x86_64; the toolchain is
    # selected purely by PATH precedence: cross_bin (a subdir of the
    # shared tools sysroot) is injected ahead of the system PATH, so the
    # bare x86_64-w64-mingw32-* tool names resolve to llvm-mingw instead
    # of the distro gcc 9.3/binutils 2.34. No cc_suffix: llvm-mingw's
    # winpthreads is the default thread model. clang emits no .refptr
    # relocations, so static deps link fine into shared ffmpeg.
    "mingw-x86_64-llvm": {
        "cross_prefix": "x86_64-w64-mingw32-",
        "cross_toolchain": "llvm-mingw/bin",
        "cc_suffix": "",
        # libtool's --tag=CXX DLL mode assembles the CRT manually with
        # -nostdlib and forgets compiler-rt (gcc-era recipe) -> ___chkstk_ms
        # undefined; whole-archive the builtins into every link.
        # {clang_rt} expands (runner) to the absolute builtins archive path,
        # passed through -Wl so libtool treats it as opaque: a bare -l gets
        # deplib-scanned (drops libtool to static-only), a bare .a argument
        # gets stripped as "static archive in shared link", and whole-archive
        # force-loads duplicate CRT symbols that lld auto-exports into every
        # import lib. As a plain linker input at the tail it just resolves
        # the chkstk refs that -nostdlib C++ DLL links lose.
        "cross_ldflags": "-Wl,{clang_rt}",
        "target_os": "mingw32",
        "shlib_dirs": ["lib", "bin"],
        "shlib_glob": "*.dll",
        "exe": "ffmpeg.exe",
        "cmake_system_name": "Windows",
        "cmake_system_processor": "AMD64",
        # try_run() support: cross cmake ports run their test binaries via
        # this emulator (wine). Without it cmake 3.25 crashes (bad_alloc)
        # when a try_run build is configured in cross mode.
        "cmake_emulator": "wine",
        # PE runtime DLLs shipped next to the binaries by cmd_install;
        # entries are [name-or-glob, src_dir] where "TOOLS:" marks a path
        # relative to the shared tools sysroot.
        "pe_runtime": [
            ["libc++.dll", "TOOLS:llvm-mingw/x86_64-w64-mingw32/bin"],
            ["libunwind.dll", "TOOLS:llvm-mingw/x86_64-w64-mingw32/bin"],
            ["libwinpthread-1.dll", "TOOLS:llvm-mingw/x86_64-w64-mingw32/bin"],
            ["libomp.dll", "TOOLS:llvm-mingw/x86_64-w64-mingw32/bin"],
        ],
        "meson_system": "windows",
        "meson_cpu_family": "x86_64",
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
