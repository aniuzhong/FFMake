"""share_pc fixup: relocate share-side pkg-config files into lib/pkgconfig.

Some projects (e.g. xcb-proto) stage their .pc files into
<prefix>/share/pkgconfig while our validator and the triplet PKG_CONFIG_PATH
only scan <prefix>/lib/pkgconfig. Copy any share-side .pc files across so
dependents resolve them.
"""

import glob
import os
import shutil


def run(ctx, key, dep):
    prefix = ctx["prefix"]
    src_dir = os.path.join(prefix, "share", "pkgconfig")
    dst_dir = os.path.join(prefix, "lib", "pkgconfig")
    if not os.path.isdir(src_dir):
        return
    os.makedirs(dst_dir, exist_ok=True)
    for pc in glob.glob(os.path.join(src_dir, "*.pc")):
        shutil.copy2(pc, dst_dir)
        print("fixup share_pc: {} -> {}".format(
            os.path.basename(pc), dst_dir))
