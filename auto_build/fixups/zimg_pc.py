"""zimg_pc fixup: zimg is C++, but its autotools .pc hides the C++
runtime in Libs.private -- consumers doing a plain (C) probe link,
e.g. ffmpeg's configure --libs resolution, need it in Libs. The shared
zimg's import lib also drags ws2_32 references. Idempotent.
"""

import os
import re


def run(ctx, key, dep):
    pc = os.path.join(ctx["prefix"], "lib", "pkgconfig", "zimg.pc")
    if not os.path.isfile(pc):
        return
    with open(pc) as f:
        body = f.read()
    if "-lc++" in body:
        return
    fixed = re.sub(r"^(Libs:.*)$", r"\1 -lc++ -lunwind -lws2_32", body,
                   count=1, flags=re.MULTILINE)
    if fixed != body:
        with open(pc, "w") as f:
            f.write(fixed)
        print("fixup zimg_pc: added c++ runtime to {}".format(pc))
