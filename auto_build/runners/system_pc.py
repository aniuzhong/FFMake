"""system-pc runner: declare a system library inside the sysroot.

Some ports require baseline libraries (zlib, ...) that we deliberately do
NOT build ourselves. In strict pkg-config mode their .pc files are hidden,
breaking Requires: chains in our own .pc files. This runner copies the
system .pc into the triplet sysroot so strict resolution succeeds while
the library itself still comes from the OS (cmake compilers find it in
/usr regardless of PKG_CONFIG_LIBDIR).
"""

import glob
import os
import shutil

from .. import paths
from .base import BuildError, Runner

# system pkg-config search dirs (Debian-likes: multiarch + share)
_SYSTEM_PC_DIRS = [
    "/usr/lib/x86_64-linux-gnu/pkgconfig",
    "/usr/share/pkgconfig",
]


class SystemPcRunner(Runner):
    system = "system-pc"

    def build(self, key, dep):
        if self.up_to_date(key, dep):
            print("dep {}: up to date, skip".format(key))
            return
        pcdir = os.path.join(self.ctx["prefix"], "lib", "pkgconfig")
        os.makedirs(pcdir, exist_ok=True)
        for pc in dep.get("pcs", [dep.get("pc", key)]):
            hits = [p for d in _SYSTEM_PC_DIRS
                    for p in glob.glob(os.path.join(d, pc + ".pc"))]
            if not hits:
                raise BuildError(
                    "system-pc {}: '{}' not found in {}".format(
                        key, pc, _SYSTEM_PC_DIRS))
            shutil.copy(hits[0], os.path.join(pcdir, pc + ".pc"))
        self.write_stamp(key, dep)
        print("dep {}: system pc declared -> {}".format(key, pcdir))
