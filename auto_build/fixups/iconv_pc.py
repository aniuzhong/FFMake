"""iconv_pc fixup: libiconv installs no pkg-config file, but the port
metadata (and any consumer resolving via pkg-config) expects iconv.pc.
Write a minimal one after install. Idempotent.
"""

import os


def run(ctx, key, dep):
    prefix = ctx["prefix"]
    pcdir = os.path.join(prefix, "lib", "pkgconfig")
    os.makedirs(pcdir, exist_ok=True)
    pc = os.path.join(pcdir, "iconv.pc")
    body = (
        "prefix={p}\n"
        "exec_prefix=${{prefix}}\n"
        "libdir=${{prefix}}/lib\n"
        "includedir=${{prefix}}/include\n\n"
        "Name: iconv\n"
        "Description: GNU charset conversion library (libiconv)\n"
        "Version: 1.17\n"
        "Libs: -L${{libdir}} -liconv\n"
        "Cflags: -I${{includedir}}\n"
    ).format(p=prefix)
    with open(pc, "w") as f:
        f.write(body)
    print("fixup iconv_pc: wrote {}".format(pc))
