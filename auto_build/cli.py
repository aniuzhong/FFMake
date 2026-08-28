"""Command-line entry of ffmpeg-auto-build.

Subcommands:
  init    Create the workspace layout and scaffolds.
  probe   L0 self-check: verify isolation of the child-process environment.
  build   [phase 1] pass through ffmpeg flags -> error-driven closed loop
          that builds missing dependencies -> compile FFmpeg.
  lock    [phase 3] persist the resolved dependency closure to lock.json
          (plus distfiles checksum verification).
  verify  [phase 4] run the smoke-test matrix for enabled features.
"""

import argparse
import json
import os
import subprocess
import sys

from . import env as env_mod
from . import paths

_GITIGNORE = "workspace/\n__pycache__/\n*.pyc\n"

_DEPS_JSON = {"schema": 1, "deps": {}}

_FLAGS_SCAFFOLD = (
    "# Flags passed through to the FFmpeg configure script (read by\n"
    "# `build` from phase 1 on).\n"
    "# One flag per line or space-separated; lines starting with '#' are\n"
    "# comments.\n"
    "# Example:\n"
    "# --enable-gpl\n"
    "# --enable-libx264\n"
)


def _write_if_absent(path, content):
    if os.path.exists(path):
        return False
    with open(path, "w") as f:
        f.write(content)
    return True


def cmd_init(_args):
    root = paths.repo_root()
    ws = paths.ensure_workspace(root)
    print("workspace: {}".format(ws))
    for name, content in (
        (".gitignore", _GITIGNORE),
        ("deps.json", json.dumps(_DEPS_JSON, indent=2) + "\n"),
        ("ffmpeg_flags.txt", _FLAGS_SCAFFOLD),
    ):
        if _write_if_absent(os.path.join(root, name), content):
            print("scaffold: {} (created)".format(name))
    print("init done")


def cmd_build(_args):
    sys.exit("build: implemented in phase 1 (error-driven loop + makefile runner)")


def cmd_lock(_args):
    sys.exit("lock: implemented in phase 3 (resolve -> lock.json + distfiles check)")


def cmd_verify(_args):
    sys.exit("verify: implemented in phase 4 (smoke matrix per enabled feature)")


def cmd_probe(_args):
    prefix = paths.prefix()

    # 1) Simulate a polluted parent environment to prove whitelist scrubbing.
    pollution = {
        "PYTHONPATH": "/tmp/leak-sim",
        "LD_LIBRARY_PATH": "/tmp/leak-sim",
        "CFLAGS": "-I/tmp/leak-sim",
        "PKG_CONFIG_LIBDIR": "/tmp/leak-sim",
    }
    saved = {k: os.environ.get(k) for k in pollution}
    os.environ.update(pollution)
    try:
        cenv = env_mod.build_child_env(prefix, strict_pkgconfig=True)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    # Residue is judged by value: a key may be intentionally re-set by us
    # (e.g. strict-mode LIBDIR); only the polluted value appearing verbatim
    # in the child counts as a leak.
    residue = [k for k in pollution if cenv.get(k) == pollution[k]]
    print("pollution injected {} -> residue in child: {}".format(
        sorted(pollution), residue if residue else "none"))

    # 2) pkg-config dual-mode probe (system zlib must exist; prefix is empty).
    for strict in (False, True):
        e = env_mod.build_child_env(prefix, strict_pkgconfig=strict)
        r = subprocess.run(["pkg-config", "--exists", "zlib"], env=e)
        mode = "strict      " if strict else "prefix-first"
        print("pkg-config[{}] system zlib visible: {}".format(
            mode, r.returncode == 0))

    # 3) Show the effective environment.
    e = env_mod.build_child_env(prefix, strict_pkgconfig=True)
    print("child PATH        = {}".format(e["PATH"]))
    print("PKG_CONFIG_PATH   = {}".format(e["PKG_CONFIG_PATH"]))
    print("PKG_CONFIG_LIBDIR = {}".format(
        e.get("PKG_CONFIG_LIBDIR", "(unset)")))


def _make_parser():
    # Prog name follows the actual entry file (e.g. build.py), not a
    # hardcoded package name.
    parser = argparse.ArgumentParser(
        prog=os.path.basename(sys.argv[0]) or "build.py",
        description="Full-source FFmpeg build system")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create the workspace layout and scaffolds"
                   ).set_defaults(fn=cmd_init)
    sub.add_parser("probe", help="L0 environment-isolation self-check"
                   ).set_defaults(fn=cmd_probe)
    sub.add_parser("build", help="[phase 1] closed-loop build of deps + FFmpeg"
                   ).set_defaults(fn=cmd_build)
    sub.add_parser("lock", help="[phase 3] persist the dependency closure"
                   ).set_defaults(fn=cmd_lock)
    sub.add_parser("verify", help="[phase 4] smoke-test matrix"
                   ).set_defaults(fn=cmd_verify)
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        # Bare invocation: show help instead of an argparse error.
        _make_parser().print_help()
        return 0
    args = _make_parser().parse_args(argv)
    return args.fn(args)
