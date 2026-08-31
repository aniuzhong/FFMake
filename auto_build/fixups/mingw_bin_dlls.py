"""mingw_bin_dlls fixup: stage runtime DLLs the port forgot to install.

Some cmake installs on mingw stage only the import library (lib/x.dll.a)
while the runtime DLL stays in the build tree (openapv staged it in an
import/ subdir, uavs3d did not install it at all). For every import lib
in <prefix>/lib, look for the matching DLL in the port build tree and
copy it to <prefix>/bin, where PE loaders (wine included) search.
Idempotent.
"""

import glob
import os
import shutil

from .. import paths


def run(ctx, key, dep):
    prefix = ctx["prefix"]
    libdir = os.path.join(prefix, "lib")
    bindir = os.path.join(prefix, "bin")
    bdir = paths.port_build_dir(ctx["root"], ctx["triplet"], key)
    if not os.path.isdir(bdir):
        return
    staged = 0
    for imp in glob.glob(os.path.join(libdir, "*.dll.a")):
        base = os.path.basename(imp)[:-len(".dll.a")]  # lib<name>
        if os.path.exists(os.path.join(bindir, base + ".dll")):
            continue
        hits = glob.glob(os.path.join(bdir, "**", base + ".dll"),
                         recursive=True)
        if hits:
            os.makedirs(bindir, exist_ok=True)
            shutil.copy2(hits[0], os.path.join(bindir, base + ".dll"))
            staged += 1
    if staged:
        print("fixup mingw_bin_dlls: {} DLL(s) -> {}".format(staged, bindir))
