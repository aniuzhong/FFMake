"""pip runner: install Python-based host tools (meson) into tools/lib.

Host tools are shared across triplets (vcpkg downloads/tools analog).
Console-entry wrappers are generated into tools/bin with a PYTHONPATH
pointing at the pip --target dir, because `pip install --target` does not
reliably create executables.

Offline seed: pip itself is a network step, so a provisioned target dir
with every wrapper present is accepted as done (the binary runner's
presence philosophy) -- a wiped stamp re-earns itself without network.
"""

import os
import sys

from .base import Runner


class PipRunner(Runner):
    system = "pip"

    def build(self, key, dep):
        if self.up_to_date(key, dep):
            print("dep {}: up to date, skip".format(key))
            return
        cfg = dep.get("pip") or {}
        tools = self.ctx["tools_prefix"]
        target = os.path.join(tools, cfg.get("target", "lib"))
        wrappers = cfg.get("wrappers", {})
        if self._seeded(target, wrappers):
            print("dep {}: provisioned (seeded), skip pip".format(key))
            self.write_stamp(key, dep)
            return
        cmd = [sys.executable, "-m", "pip", "install",
               "--target", target, "--upgrade"] + list(cfg.get("require", []))
        self._run_net(cmd, self.ctx["root"],
                      os.path.join(self.ctx["logs"], key + "_pip.log"))
        for name, spec in sorted(wrappers.items()):
            module, func = spec.split(":")
            self._write_wrapper(os.path.join(tools, "bin", name),
                                target, module, func)
        self.write_stamp(key, dep)
        print("dep {}: installed into {}".format(key, target))

    @staticmethod
    def _seeded(target, wrappers):
        if not os.path.isdir(target) or not os.listdir(target):
            return False
        for name in wrappers:
            if not os.path.exists(os.path.join(
                    os.path.dirname(target), "bin", name)):
                return False
        return True

    @staticmethod
    def _write_wrapper(path, target, module, func):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        script = (
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "sys.path.insert(0, {target!r})\n"
            "from {module} import {func}\n"
            "sys.exit({func}())\n"
        ).format(target=target, module=module, func=func)
        with open(path, "w") as f:
            f.write(script)
        os.chmod(path, 0o755)
