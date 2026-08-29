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
        # (e.g. vulkan-loader needs system x11/xcb dev files)
        strict = bool(dep.get("strict_pkgconfig", True))
        env = self.env(strict=strict)
        subst = {
            "src": os.path.abspath(src),
            "bdir": os.path.abspath(bdir),
            "tools": self.ctx["tools_prefix"],
            "prefix": prefix,
            "jobs": str(self.ctx["jobs"]),
        }
        srcdir = os.path.abspath(os.path.join(
            src, dep.get("source_dir", "")))
        args = ["cmake", "-S", srcdir, "-B", bdir,
                "-DCMAKE_INSTALL_PREFIX=" + prefix,
                "-DCMAKE_BUILD_TYPE=Release"] + \
               [a.format(**subst) for a in dep.get("cmake_args", [])]
        self.run(args, bdir, os.path.join(logs, "configure.log"), env=env)
        self.run(["cmake", "--build", bdir, "-j", str(self.ctx["jobs"])],
                 bdir, os.path.join(logs, "build.log"), env=env)
        self.run(["cmake", "--install", bdir], bdir,
                 os.path.join(logs, "install.log"), env=env)
        self.write_stamp(key, dep)
        print("dep {}: built & installed -> {}".format(key, prefix))
