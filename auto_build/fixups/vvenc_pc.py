"""vvenc_pc fixup: libvvenc is C++; consumers linking it need the C++
runtime, but its generated .pc lists no runtime libs, so plain (C) probe
links -- e.g. ffmpeg's configure -- fail with undefined operator-new and
unwind symbols. Append the llvm-mingw runtime + ws2_32 libs to Libs. Idempotent.
"""

import os
import re


def run(ctx, key, dep):
    pc = os.path.join(ctx["prefix"], "lib", "pkgconfig", "libvvenc.pc")
    if not os.path.isfile(pc):
        return
    with open(pc) as f:
        body = f.read()
    fixed = re.sub(r"^(Libs:.*)$", r"\1 -lc++ -lunwind -lws2_32 -lpthread -lm", body,
                   count=1, flags=re.MULTILINE)
    if fixed != body:
        with open(pc, "w") as f:
            f.write(fixed)
        print("fixup vvenc_pc: added c++ runtime to {}".format(pc))
