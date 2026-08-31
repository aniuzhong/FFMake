"""vpx_pc fixup: libvpx installs static-only on mingw targets (its
configure rejects --enable-shared there). Its pkg-config Libs then lack
the pthread dependency, which consumers linking the static archive need.
Append the runtime libs to the Libs line. Idempotent.
"""

import os
import re


def run(ctx, key, dep):
    pc = os.path.join(ctx["prefix"], "lib", "pkgconfig", "vpx.pc")
    if not os.path.isfile(pc):
        return
    with open(pc) as f:
        body = f.read()
    fixed = re.sub(r"^(Libs:.*)$", r"\1 -lpthread -lm", body,
                   count=1, flags=re.MULTILINE)
    if fixed != body:
        with open(pc, "w") as f:
            f.write(fixed)
        print("fixup vpx_pc: added pthread/m to {}".format(pc))
