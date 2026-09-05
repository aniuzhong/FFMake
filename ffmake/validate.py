"""L2 gate: post-install invariant validation.

Every dep must pass before the configure loop may retry, so install bugs
(missing .pc, multiarch libdir, tool not in bin/) surface as actionable
errors here instead of as confusing downstream configure failures.
Triplet-aware: ELF .so for linux, DLLs for mingw; host tools land in the
shared tools sysroot rather than a triplet sysroot.
"""

import glob
import os
import subprocess

from . import env as env_mod
from .runners.base import BuildError


def is_installed(prefix, tools_prefix, key, dep):
    """Cheap inventory check used by `port list` (no validation)."""
    if dep.get("tool"):
        tool_bin = dep.get("tool_bin", key)
        return os.path.isfile(os.path.join(tools_prefix, "bin", tool_bin))
    pc = dep.get("pc", key)
    return os.path.isfile(os.path.join(prefix, "lib", "pkgconfig",
                                       pc + ".pc"))


def validate_dep(ctx, key, dep):
    if dep.get("tool"):
        tool_bin = dep.get("tool_bin", "bin/" + key)
        path = os.path.join(ctx["tools_prefix"], tool_bin)
        if not os.path.isfile(path):
            raise BuildError(
                "tool '{}' missing after install: {}".format(key, path))
        print("validate {}: tool ok ({})".format(key, path))
        return

    prefix = ctx["prefix"]
    pc = dep.get("pc", key)
    pcfile = os.path.join(prefix, "lib", "pkgconfig", pc + ".pc")
    if not os.path.isfile(pcfile):
        raise BuildError("{}: missing {} (runner install bug?)".format(
            key, pcfile))

    # strict mode: the .pc must resolve from the triplet sysroot alone
    env = env_mod.build_child_env(prefix, strict_pkgconfig=True)
    rc = subprocess.run(["pkg-config", "--exists", pc],
                        env=env).returncode
    if rc != 0:
        raise BuildError(
            "{}: pkg-config cannot resolve '{}' in strict mode "
            "(wrong libdir or broken .pc)".format(key, pc))

    # the shared-library check is a CLOSURE-level invariant, not a
    # per-port one: headers-only ports legitimately install no .so, and
    # the old system only passed them because the glob scanned the whole
    # sysroot in build order. See closure_shlib_gate().
    from . import facts
    facts.backfill_installed(ctx, key, dep)
    print("validate {}: pc + strict pkg-config ok ({})".format(
        key, ctx["triplet"]))


def closure_shlib_gate(ctx):
    """At least one shared library must exist in the sysroot once the
    closure is built (catches wholesale linkage breakage)."""
    import glob as _glob
    shlib_glob = ctx["triplet_cfg"]["shlib_glob"]
    hits = []
    for d in ctx["triplet_cfg"]["shlib_dirs"]:
        hits += _glob.glob(os.path.join(ctx["prefix"], d, shlib_glob))
    if not hits:
        raise BuildError(
            "closure: no shared libraries matching {} in {} -- linkage "
            "is broken".format(shlib_glob, ctx["prefix"]))
    print("validate: closure shlib gate ok ({} artifacts)".format(
        len(hits)))
