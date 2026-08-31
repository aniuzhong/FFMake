"""meson runner: meson setup + ninja back end, out-of-tree per port.

-Dlibdir=lib is forced to keep everything in the unified sysroot: meson's
default libdir on Debian-likes is the multiarch dir, which breaks our
pkg-config strict mode. Host tools (meson itself + ninja) come from
workspace/tools via PATH (L0 env).
"""

import os

from .base import Runner


class MesonRunner(Runner):
    system = "meson"

    def build(self, key, dep):
        if self.up_to_date(key, dep):
            print("dep {}: up to date, skip".format(key))
            return
        prefix = self.install_prefix(dep)
        src, bdir, logs = self.prepare(key, dep)
        if dep.get("prefixup"):
            # pre-build source repair, same semantics as other runners
            subst = {
                "src": os.path.abspath(src),
                "bdir": os.path.abspath(bdir),
                "tools": self.ctx["tools_prefix"],
                "prefix": prefix,
                "jobs": str(self.ctx["jobs"]),
            }
            self.run(["bash", "-c", dep["prefixup"].format(**subst)],
                     src, os.path.join(logs, "prefixup.log"),
                     env=self.env(strict=False))
        # strict_pkgconfig:false opts a port into system .pc visibility
        # (e.g. libvdpau needs system x11/xext/dri2proto dev files)
        strict = bool(dep.get("strict_pkgconfig", True))
        env = self.env(strict=strict)
        srcdir = os.path.abspath(os.path.join(
            src, dep.get("source_dir", "")))
        args = ["meson", "setup", bdir, srcdir,
                "--prefix=" + prefix,
                "--buildtype=release",
                "--default-library=shared",
                "-Dlibdir=lib"] + list(dep.get("meson_args", []))
        # cross triplets: triplet-declared cross file (binaries +
        # host_machine); pkg-config stays the host binary with the
        # target sysroot pinned via PKG_CONFIG_LIBDIR
        cross = self.cross_file("meson", bdir)
        if cross:
            args += ["--cross-file=" + cross]
        self.run(args, bdir, os.path.join(logs, "configure.log"), env=env)
        self.run(["ninja", "-C", bdir, "-j", str(self.ctx["jobs"])], bdir,
                 os.path.join(logs, "build.log"), env=env)
        self.run(["ninja", "-C", bdir, "install"], bdir,
                 os.path.join(logs, "install.log"), env=env)
        self.write_stamp(key, dep)
        print("dep {}: built & installed -> {}".format(key, prefix))
