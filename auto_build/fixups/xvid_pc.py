"""xvid_pc fixup: xvid's build-generic install ships no pkg-config file
(ffmpeg probes it via check_lib, not pkg-config; the .pc exists purely
so the validate gate can resolve the port). Write a minimal one.
Idempotent.
"""

import os


def run(ctx, key, dep):
    prefix = ctx["prefix"]
    pcdir = os.path.join(prefix, "lib", "pkgconfig")
    os.makedirs(pcdir, exist_ok=True)
    pc = os.path.join(pcdir, "libxvid.pc")
    if os.path.isfile(pc):
        return
    body = (
        "prefix={p}\n"
        "exec_prefix=${{prefix}}\n"
        "libdir=${{prefix}}/lib\n"
        "includedir=${{prefix}}/include\n\n"
        "Name: libxvid\n"
        "Description: Xvid MPEG-4 codec\n"
        "Version: 1.3.7\n"
        "Libs: -L${{libdir}} -lxvidcore\n"
        "Cflags: -I${{includedir}}\n"
    ).format(p=prefix)
    with open(pc, "w") as f:
        f.write(body)
    print("fixup xvid_pc: wrote {}".format(pc))
