"""pocketsphinx_hdr fixup: normalize pocketsphinx's header layout.

Some 5.x installs drop pocketsphinx.h at include/ root while consumers
include <pocketsphinx/pocketsphinx.h>. Move it into place. Idempotent.
"""

import os
import shutil


def run(ctx, key, dep):
    inc = os.path.join(ctx["prefix"], "include")
    src = os.path.join(inc, "pocketsphinx.h")
    sub = os.path.join(inc, "pocketsphinx")
    dst = os.path.join(sub, "pocketsphinx.h")
    if os.path.exists(src) and not os.path.exists(dst):
        os.makedirs(sub, exist_ok=True)
        shutil.move(src, dst)
        print("fixup pocketsphinx_hdr: {} -> {}".format(src, dst))
