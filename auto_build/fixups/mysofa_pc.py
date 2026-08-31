"""mysofa_pc fixup: libmysofa's cmake installs no mysofa.pc, but FFmpeg's
configure resolves libmysofa via pkg-config. Write a minimal .pc after
install; also alias libmysofa_shared.dll.a to libmysofa.dll.a so plain
-lmysofa resolves (cmake names the import lib after the target).
"""

import glob
import os
import shutil


def run(ctx, key, dep):
    prefix = ctx["prefix"]
    libdir = os.path.join(prefix, "lib")
    pcdir = os.path.join(libdir, "pkgconfig")
    os.makedirs(pcdir, exist_ok=True)
    # import-lib alias: target libmysofa_shared -> linkable as -lmysofa
    for imp in glob.glob(os.path.join(libdir, "libmysofa_shared.dll.a")):
        shutil.copy2(imp, os.path.join(libdir, "libmysofa.dll.a"))
    pc = os.path.join(pcdir, "mysofa.pc")
    body = (
        "prefix={p}\n"
        "libdir=${{prefix}}/lib\n"
        "includedir=${{prefix}}/include\n\n"
        "Name: mysofa\n"
        "Description: SOFA (Spatially Oriented Format for Acoustics) reader\n"
        "Version: 1.3.2\n"
        "Cflags: -I${{includedir}}\n"
        "Libs: -L${{libdir}} -lmysofa -lz -lm\n"
    ).format(p=prefix)
    with open(pc, "w") as f:
        f.write(body)
    print("fixup mysofa_pc: wrote {}".format(pc))
