"""zimg_pc fixup: zimg is C++, but its autotools .pc hides the C++
runtime in Libs.private -- consumers doing a plain (C) probe link,
e.g. ffmpeg's configure --libs resolution, need it in Libs. Triplet-aware:
mingw gets the llvm-mingw runtime + ws2_32, linux gets libstdc++. Also
strips wrong-triplet leftovers from a previously polluted .pc. Idempotent.
"""

import os
import re

_MINGW_LIBS = ["-lc++", "-lunwind", "-lws2_32"]
_LINUX_LIBS = ["-lstdc++"]


def run(ctx, key, dep):
    pc = os.path.join(ctx["prefix"], "lib", "pkgconfig", "zimg.pc")
    if not os.path.isfile(pc):
        return
    mingw = "mingw" in ctx["triplet"]
    wanted = _MINGW_LIBS if mingw else _LINUX_LIBS
    wrong = _LINUX_LIBS if mingw else _MINGW_LIBS
    with open(pc) as f:
        body = f.read()

    def _strip(text, libs):
        for lib in libs:
            text = re.sub(r"(?<=\s){}(?=\s|$)".format(re.escape(lib)), "",
                          text, flags=re.MULTILINE)
        return re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)

    fixed = _strip(body, wrong)
    m = re.search(r"^(Libs:.*)$", fixed, flags=re.MULTILINE)
    libs_line = m.group(1)
    missing = [lib for lib in wanted if lib not in libs_line]
    if missing:
        fixed = fixed.replace(libs_line,
                              (libs_line + " " + " ".join(missing)).rstrip())
    if fixed != body:
        with open(pc, "w") as f:
            f.write(fixed)
        print("fixup zimg_pc: runtime libs for {} -> {}".format(
            ctx["triplet"], " ".join(wanted)))
