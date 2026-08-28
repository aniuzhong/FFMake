"""makefile runner: classic ./configure && make && make install projects.

Deps build in-tree inside their vendor src dir (pragmatic for small
third-party trees); a stamp mismatch triggers a full re-fetch, which keeps
the trees from accumulating stale build residue. FFmpeg itself stays
out-of-tree because its upstream git repo must remain pristine.
"""

from .base import BuildError, Runner


class MakefileRunner(Runner):
    system = "makefile"

    def build(self, key, dep):
        if self.up_to_date(key, dep):
            print("dep {}: up to date, skip".format(key))
            return
        src = self.fetch(key, dep)
        # joined --prefix=... form: required by FFmpeg, safest everywhere
        args = ["./configure", "--prefix=" + self.ctx["prefix"]] + \
               list(dep.get("configure_args", []))
        self.run(args, src, key + "_configure.log")
        self.run(["make", "-j", str(self.ctx["jobs"])], src,
                 key + "_make.log")
        self.run(["make", "install"], src, key + "_install.log")
        self.write_stamp(key, dep)
        print("dep {}: built & installed".format(key))
