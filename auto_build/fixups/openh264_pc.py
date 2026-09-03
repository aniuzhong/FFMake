"""openh264_pc fixup: openh264's static archive needs the C++ runtime and
thread/socket libs at link time, but its generated .pc lists none of them,
so plain (C) probe links -- e.g. ffmpeg's configure -- fail. Append the
llvm-mingw runtime libs to Libs. Idempotent. mingw-only: on the linux
triplet the upstream-generated .pc is already link-clean -- appending
-lc++/-lwinpthread/-lws2_32 there poisons every probe link (2026-09-02
cold-build lesson: the global registration needs a triplet guard).
"""

import os
import re


def run(ctx, key, dep):
    if not ctx["triplet"].startswith("mingw"):
        return
    pc = os.path.join(ctx["prefix"], "lib", "pkgconfig", "openh264.pc")
    if not os.path.isfile(pc):
        return
    with open(pc) as f:
        body = f.read()
    extra = "-lc++ -lunwind -lwinpthread -lws2_32"
    if extra in body:
        return
    fixed = re.sub(r"^(Libs:.*)$", "\\1 " + extra, body,
                   count=1, flags=re.MULTILINE)
    with open(pc, "w") as f:
        f.write(fixed)
    print("fixup openh264_pc: added runtime libs to {}".format(pc))
