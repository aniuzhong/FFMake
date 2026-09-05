"""custom runner: declarative shell steps for non-standard builds.

deps.json entry provides "steps": a list of shell command strings executed
with bash -c inside the per-port build dir. Placeholders expanded:
  {src}    vendor source dir
  {bdir}   per-port build dir
  {tools}  host tools prefix
  {prefix} install prefix (per-triplet, or tools for tool deps)
  {jobs}   parallel jobs
Used e.g. for ninja's configure.py --bootstrap.
"""

import os

from .base import Runner


class CustomRunner(Runner):
    system = "custom"

    def build(self, key, dep):
        if self.up_to_date(key, dep):
            print("dep {}: up to date, skip".format(key))
            return
        prefix = self.install_prefix(dep)
        src, bdir, logs = self.prepare(key, dep)
        subst = {
            "src": os.path.abspath(src),
            "bdir": os.path.abspath(bdir),
            "tools": self.ctx["tools_prefix"],
            "prefix": prefix,
            "jobs": str(self.ctx["jobs"]),
        }
        if dep.get("prefixup"):
            self.run(["bash", "-c", dep["prefixup"].format(**subst)], src,
                     os.path.join(logs, "prefixup.log"),
                     env=self.env(strict=False))
        for i, step in enumerate(dep.get("steps", []), start=1):
            self.run(["bash", "-c", step.format(**subst)], bdir,
                     "{}/step{:02d}.log".format(logs, i))
        self.write_stamp(key, dep)
        print("dep {}: built & installed -> {}".format(key, prefix))
