"""mp3lame_pc fixup: lame 3.100's autotools install ships no pkg-config
file (distros patch one in), but FFmpeg's configure resolves libmp3lame
via pkg-config. Write a minimal .pc after install.
"""

import os


def run(ctx, key, dep):
    prefix = ctx["prefix"]
    pcdir = os.path.join(prefix, "lib", "pkgconfig")
    os.makedirs(pcdir, exist_ok=True)
    pc = os.path.join(pcdir, "mp3lame.pc")
    body = (
        "prefix={p}\n"
        "libdir=${{prefix}}/lib\n"
        "includedir=${{prefix}}/include\n\n"
        "Name: mp3lame\n"
        "Description: LAME Ain't an MP3 Encoder\n"
        "Version: 3.100\n"
        "Cflags: -I${{includedir}}\n"
        "Libs: -L${{libdir}} -lmp3lame\n"
    ).format(p=prefix)
    with open(pc, "w") as f:
        f.write(body)
    print("fixup mp3lame_pc: wrote {}".format(pc))
