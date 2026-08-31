"""frei0r_pc fixup: frei0r's cmake installs only the frei0r.h header (the
plugin API) and no pkg-config file, but the validate gate resolves every
port through one. Write a minimal Cflags-only pc (header-only port
pattern, lesson #68). Idempotent.
"""

import os


def run(ctx, key, dep):
    prefix = ctx["prefix"]
    pcdir = os.path.join(prefix, "lib", "pkgconfig")
    os.makedirs(pcdir, exist_ok=True)
    pc = os.path.join(pcdir, "frei0r.pc")
    if os.path.isfile(pc):
        return
    body = (
        "prefix={p}\n"
        "libdir=${{prefix}}/lib\n"
        "includedir=${{prefix}}/include\n\n"
        "Name: frei0r\n"
        "Description: Frei0r plugin API\n"
        "Version: 2.3.3\n"
        "Cflags: -I${{includedir}}\n"
    ).format(p=prefix)
    with open(pc, "w") as f:
        f.write(body)
    print("fixup frei0r_pc: wrote {}".format(pc))
