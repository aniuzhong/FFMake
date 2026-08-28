"""makefile runner: classic ./configure && make && make install projects.

Out-of-tree per-port builds (vcpkg buildtrees style): vendor src/ stays
pristine, the build tree lives in workspace/build/<key>/ with colocated
logs. A stamp mismatch wipes only the build tree unless the source
rev/url changed, in which case src/ is re-fetched too.
"""

import os

from .base import Runner


class MakefileRunner(Runner):
    system = "makefile"

    def build(self, key, dep):
        if self.up_to_date(key, dep):
            print("dep {}: up to date, skip".format(key))
            return
        src, bdir, logs = self.prepare(key, dep)
        # joined --prefix=... form: required by FFmpeg, safest everywhere
        args = [os.path.join(os.path.abspath(src), "configure"),
                "--prefix=" + self.ctx["prefix"]] + \
               list(dep.get("configure_args", []))
        self.run(args, bdir, os.path.join(logs, "configure.log"))
        self.run(["make", "-j", str(self.ctx["jobs"])], bdir,
                 os.path.join(logs, "make.log"))
        self.run(["make", "install"], bdir, os.path.join(logs, "install.log"))
        self.write_stamp(key, dep)
        print("dep {}: built & installed".format(key))
