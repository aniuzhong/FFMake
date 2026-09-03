"""glib_pc fixup: the sysroot copy of glib-2.0.pc keeps the host's
Requires.private verbatim (libpcre on pcre1-era hosts, libpcre2-8 on
noble) -- strict --exists would then demand whichever name the HOST
happens to use, making the declaration host-dependent (Kylin vs noble
divergence, 2026-09-02 cold-build lesson). glib is only ever linked
dynamically here (lensfun's hardcoded GLIB2_* paths), so strip the
private-requirement lines: the declaration decouples from the host
distro generation entirely. Caveat: pkg-config --static consumers of
this .pc lose the private libs -- none exist in this closure.
"""

import os


def run(ctx, key, dep):
    pcdir = os.path.join(ctx["prefix"], "lib", "pkgconfig")
    pc = os.path.join(pcdir, "glib-2.0.pc")
    with open(pc) as f:
        lines = [ln for ln in f if not ln.startswith("Requires.private:")]
    with open(pc, "w") as f:
        f.writelines(lines)
    print("fixup glib_pc: stripped private requires -> {}".format(pc))
