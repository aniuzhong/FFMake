"""cmake runner: cmake -S/-B configure + build + install, out-of-tree.

Per-port build tree lives in workspace/build/<ns>/<key>/; per-port args
come from deps.json "cmake_args". Cross triplets would need a toolchain
file (phase 3 stretch); native linux is the current scope.
"""

import os

from .base import Runner


class CmakeRunner(Runner):
    system = "cmake"

    def build(self, key, dep):
        if self.up_to_date(key, dep):
            print("dep {}: up to date, skip".format(key))
            return
        prefix = self.install_prefix(dep)
        src, bdir, logs = self.prepare(key, dep)
        srcdir = os.path.abspath(os.path.join(
            src, dep.get("source_dir", "")))
        args = ["cmake", "-S", srcdir, "-B", bdir,
                "-DCMAKE_INSTALL_PREFIX=" + prefix,
                "-DCMAKE_BUILD_TYPE=Release"] + \
               list(dep.get("cmake_args", []))
        self.run(args, bdir, os.path.join(logs, "configure.log"))
        self.run(["cmake", "--build", bdir, "-j", str(self.ctx["jobs"])],
                 bdir, os.path.join(logs, "build.log"))
        self.run(["cmake", "--install", bdir], bdir,
                 os.path.join(logs, "install.log"))
        self.write_stamp(key, dep)
        print("dep {}: built & installed -> {}".format(key, prefix))
