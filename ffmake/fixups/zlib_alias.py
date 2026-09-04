"""zlib_alias fixup: alias cmake's zlib import library.

cmake names the mingw import lib after the target (libzlib.dll.a) while
consumers link plain -lz (libz.dll.a). Copy when present; no-op on ELF
triplets where libzlib.dll.a does not exist. Idempotent.
"""

import os
import shutil


def run(ctx, key, dep):
    lib = os.path.join(ctx["prefix"], "lib")
    src = os.path.join(lib, "libzlib.dll.a")
    dst = os.path.join(lib, "libz.dll.a")
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print("fixup zlib_alias: {} -> {}".format(src, dst))
