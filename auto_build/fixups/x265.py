"""x265 fixup: repair the cmake install (the famous x265 packaging bug).

x265's cmake installs only the static archive into <prefix>/lib and skips
both the shared objects and the .pc file, breaking -lx265 consumers. This
hook (mirroring vcpkg's pkgconfig.diff/linkage.diff):
  1. copies libx265.so.* from the build tree into <prefix>/lib
  2. creates the libx265.so symlink for -lx265
  3. writes a correct x265.pc
Linux triplets only: mingw x265 installs differently (x265.dll import lib)
and is out of scope until a mingw x265 port is needed.
"""

import glob
import os
import shutil

from .. import paths
from ..runners.base import BuildError


def run(ctx, key, dep):
    if ctx["triplet_cfg"]["target_os"] != "linux":
        return
    prefix = ctx["prefix"]
    libdir = os.path.join(prefix, "lib")
    pcdir = os.path.join(prefix, "lib", "pkgconfig")
    pc = os.path.join(pcdir, "x265.pc")

    # 1) shared objects: copy from build tree if not installed
    bdir = paths.port_build_dir(ctx["root"], ctx["triplet"], key)
    sonames = sorted(glob.glob(os.path.join(bdir, "**", "libx265.so.*"),
                               recursive=True))
    if sonames and not glob.glob(os.path.join(libdir, "libx265.so.*")):
        for so in sonames:
            shutil.copy2(so, libdir)
    installed = sorted(glob.glob(os.path.join(libdir, "libx265.so.*")),
                       key=lambda p: -len(p))
    if not installed:
        raise BuildError("x265 fixup: no libx265.so.* found in build tree")

    # 2) dev symlink for -lx265
    link = os.path.join(libdir, "libx265.so")
    if not os.path.islink(link):
        target = os.path.basename(installed[0])  # longest name = real lib
        os.symlink(target, link)

    # 3) pkg-config file
    version = (dep.get("hook") or {}).get("pc_version", "3.6")
    os.makedirs(pcdir, exist_ok=True)
    with open(pc, "w") as f:
        f.write(
            "prefix={p}\n"
            "exec_prefix=${{prefix}}\n"
            "libdir=${{exec_prefix}}/lib\n"
            "includedir=${{prefix}}/include\n"
            "\n"
            "Name: x265\n"
            "Description: H.265/HEVC video encoder\n"
            "Version: {v}\n"
            "Libs: -L${{libdir}} -lx265\n"
            "Libs.private: -lstdc++ -lm -lrt -ldl -lpthread\n"
            "Cflags: -I${{includedir}}\n".format(p=prefix, v=version))
    print("fixup x265: shared lib + symlink + x265.pc written")
