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
        args = ["meson", "setup", bdir, os.path.abspath(src),
                "--prefix=" + prefix,
                "--buildtype=release",
                "--default-library=shared",
                "-Dlibdir=lib"] + list(dep.get("meson_args", []))
        self.run(args, bdir, os.path.join(logs, "configure.log"))
        self.run(["ninja", "-C", bdir, "-j", str(self.ctx["jobs"])], bdir,
                 os.path.join(logs, "build.log"))
        self.run(["ninja", "-C", bdir, "install"], bdir,
                 os.path.join(logs, "install.log"))
        self.write_stamp(key, dep)
        print("dep {}: built & installed -> {}".format(key, prefix))
