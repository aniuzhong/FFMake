"""lept_pc fixup: normalize leptonica's pkg-config file name.

Release-configured builds write lept_<CMAKE_BUILD_TYPE>.pc; consumers
resolve plain 'lept'. Rename when needed. Idempotent.
"""

import os


def run(ctx, key, dep):
    pcdir = os.path.join(ctx["prefix"], "lib", "pkgconfig")
    src = os.path.join(pcdir, "lept_Release.pc")
    dst = os.path.join(pcdir, "lept.pc")
    if os.path.exists(src) and not os.path.exists(dst):
        os.replace(src, dst)
        print("fixup lept_pc: {} -> {}".format(src, dst))
