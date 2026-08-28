"""L2 gate: post-install invariant validation.

Every dep must pass before the configure loop may retry, so install bugs
(missing .pc, multiarch libdir, tool not in bin/) surface as actionable
errors here instead of as confusing downstream configure failures.
"""

import glob
import os
import subprocess

from . import env as env_mod
from .runners.base import BuildError


def is_installed(prefix, key, dep):
    """Cheap inventory check used by `port list` (no validation)."""
    if dep.get("tool"):
        return os.path.isfile(os.path.join(prefix, "bin",
                                           dep.get("tool_bin", key)))
    pc = dep.get("pc", key)
    return os.path.isfile(os.path.join(prefix, "lib", "pkgconfig",
                                       pc + ".pc"))


def validate_dep(prefix, key, dep):
    if dep.get("tool"):
        tool_bin = dep.get("tool_bin", key)
        path = os.path.join(prefix, "bin", tool_bin)
        if not os.path.isfile(path):
            raise BuildError(
                "tool '{}' missing after install: {}".format(key, path))
        print("validate {}: tool ok ({})".format(key, path))
        return

    pc = dep.get("pc", key)
    pcfile = os.path.join(prefix, "lib", "pkgconfig", pc + ".pc")
    if not os.path.isfile(pcfile):
        raise BuildError("{}: missing {} (runner install bug?)".format(
            key, pcfile))

    # strict mode: the .pc must resolve from the unified prefix alone
    env = env_mod.build_child_env(prefix, strict_pkgconfig=True)
    rc = subprocess.run(["pkg-config", "--exists", pc],
                        env=env).returncode
    if rc != 0:
        raise BuildError(
            "{}: pkg-config cannot resolve '{}' in strict mode "
            "(wrong libdir or broken .pc)".format(key, pc))

    if not glob.glob(os.path.join(prefix, "lib", "lib*.so*")):
        raise BuildError(
            "{}: no shared libraries found in {}/lib".format(key, prefix))
    print("validate {}: pc + strict pkg-config + shared libs ok".format(key))
