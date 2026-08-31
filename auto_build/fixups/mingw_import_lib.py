"""mingw_import_lib fixup: normalize import-library locations.

Some cmake projects on mingw stage PE import libraries (.dll.a) into a
non-standard subdir (e.g. openapv -> lib/<name>/import/) while the .pc
file links plain -l<name> from <prefix>/lib. Move any lib/*/import/*.dll.a
up to <prefix>/lib so pkg-config consumers resolve them. Idempotent.
"""

import glob
import os
import shutil


def run(ctx, key, dep):
    lib = os.path.join(ctx["prefix"], "lib")
    moved = 0
    for sub in glob.glob(os.path.join(lib, "*", "import")):
        for imp in glob.glob(os.path.join(sub, "*.dll.a")):
            dst = os.path.join(lib, os.path.basename(imp))
            shutil.copy2(imp, dst)
            moved += 1
    if moved:
        print("fixup mingw_import_lib: {} import lib(s) -> {}".format(
            moved, lib))
