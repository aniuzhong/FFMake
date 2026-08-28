"""Command-line entry of ffmake (CMake-aligned lifecycle verbs).

  configure  Pass through FFmpeg configure flags; build missing deps via
             the error-driven loop until configure succeeds.
  build      Compile FFmpeg in the out-of-tree build dir.
  install    Install FFmpeg into the unified prefix.
  test       Smoke-test the installed binaries.
  all        Chain configure -> build -> install -> test.

Non-lifecycle: probe (L0 diagnostics), init (optional workspace bootstrap).
"""

import argparse
import os
import subprocess
import sys

from . import env as env_mod
from . import loop
from . import paths
from . import validate


def _die(msg):
    sys.exit("ffmake: " + str(msg))


def _ctx(args):
    root = paths.repo_root()
    paths.ensure_workspace(root)  # lazy creation; `init` is not required
    src = args.ffmpeg_src or os.environ.get("FFMAKE_FFMPEG_SRC")
    if src:
        # explicit source must exist; otherwise loop resolves lazily:
        # workspace/src/ffmpeg, auto-cloning the pinned rev if absent
        src = os.path.abspath(src)
        if not os.path.isfile(os.path.join(src, "configure")):
            _die("FFmpeg source not found at {}\n"
                 "hint: pass --ffmpeg-src or set FFMAKE_FFMPEG_SRC, "
                 "or leave unset to use workspace/src/ffmpeg".format(src))
    return {
        "root": root,
        "prefix": paths.prefix(root),
        "logs": paths.logs(root),
        "jobs": args.jobs or os.cpu_count() or 4,
        "ffmpeg_src": src,
    }


def cmd_configure(args):
    loop.configure_loop(_ctx(args))


def cmd_build(args):
    ctx = _ctx(args)
    out = paths.ffmpeg_out(ctx["root"])
    if not os.path.exists(os.path.join(out, "ffbuild", "config.mak")):
        _die("no configuration in {} -- run 'configure' first".format(out))
    log = os.path.join(ctx["logs"], "ffmpeg_make.log")
    # L0 env is mandatory for every subprocess: PATH must prefer the
    # prefix toolchain (nasm 2.16) over the system one (2.14).
    env = env_mod.build_child_env(ctx["prefix"])
    with open(log, "w") as f:
        rc = subprocess.run(["make", "-j", str(ctx["jobs"])], cwd=out,
                            env=env, stdout=f, stderr=subprocess.STDOUT
                            ).returncode
    if rc != 0:
        _die("build failed (see {})".format(log))
    print("build: OK")


def cmd_install(args):
    ctx = _ctx(args)
    out = paths.ffmpeg_out(ctx["root"])
    log = os.path.join(ctx["logs"], "ffmpeg_install.log")
    env = env_mod.build_child_env(ctx["prefix"])
    with open(log, "w") as f:
        rc = subprocess.run(["make", "install"], cwd=out, env=env,
                            stdout=f, stderr=subprocess.STDOUT).returncode
    if rc != 0:
        _die("install failed (see {})".format(log))
    print("install: OK -> {}".format(ctx["prefix"]))


def cmd_test(args):
    ctx = _ctx(args)
    ffmpeg = os.path.join(ctx["prefix"], "bin", "ffmpeg")
    if not os.path.isfile(ffmpeg):
        _die("installed ffmpeg not found at {} -- run 'install' first"
             .format(ffmpeg))
    # rpath (baked via extra-ldflags) makes this run without LD_LIBRARY_PATH
    env = env_mod.build_child_env(ctx["prefix"])
    out_mp4 = os.path.join(ctx["logs"], "smoke_x264.mp4")
    rc = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc2=duration=0.5:size=640x360:rate=30",
         "-c:v", "libx264", "-y", out_mp4],
        env=env).returncode
    if rc != 0 or not os.path.exists(out_mp4) or os.path.getsize(out_mp4) == 0:
        _die("smoke encode failed")
    print("test: OK -> {} ({} bytes)".format(out_mp4,
                                             os.path.getsize(out_mp4)))


def cmd_all(args):
    cmd_configure(args)
    cmd_build(args)
    cmd_install(args)
    cmd_test(args)


def cmd_port_install(args):
    ctx = _ctx(args)
    for key in args.keys:
        loop.build_dep(ctx, key)


def cmd_port_list(_args):
    root = paths.repo_root()
    paths.ensure_workspace(root)
    data, deps, index = loop.load_deps(root)
    prefix = paths.prefix(root)
    print("{:<12} {:<10} {:<10} {}".format(
        "PORT", "SYSTEM", "STATUS", "SOURCE"))
    for key, dep in sorted(deps.items()):
        status = "installed" if validate.is_installed(prefix, key, dep) \
            else "missing"
        source = dep.get("source") or {}
        where = source.get("rev") or source.get("url") or ""
        print("{:<12} {:<10} {:<10} {}".format(
            key, dep.get("system", "-"), status, where))


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


def cmd_init(_args):
    root = paths.repo_root()
    ws = paths.ensure_workspace(root)
    print("workspace: {}".format(ws))


def _add_common(p):
    p.add_argument("--ffmpeg-src", default=None,
                   help="FFmpeg source tree (default: $FFMAKE_FFMPEG_SRC "
                        "or ../ffmpeg)")
    p.add_argument("-j", "--jobs", type=int, default=0,
                   help="parallel jobs (default: cpu count)")


def _make_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(sys.argv[0]) or "ffmake.py",
        description="Full-source FFmpeg build system "
                    "(CMake-aligned lifecycle verbs)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name, help_, fn in (
        ("configure",
         "build missing deps (error-driven loop) and make FFmpeg's "
         "configure pass", cmd_configure),
        ("build", "compile FFmpeg out-of-tree", cmd_build),
        ("install", "install FFmpeg into the unified prefix", cmd_install),
        ("test", "smoke-test the installed binaries", cmd_test),
        ("all", "configure -> build -> install -> test", cmd_all),
    ):
        sp = sub.add_parser(name, help=help_)
        _add_common(sp)
        sp.set_defaults(fn=fn)

    sub.add_parser("probe", help="L0 environment-isolation self-check"
                   ).set_defaults(fn=cmd_probe)
    sub.add_parser("init", help="[optional] create the workspace layout now"
                   ).set_defaults(fn=cmd_init)

    # vcpkg-style dependency (port) management
    port = sub.add_parser("port", help="dependency (port) management")
    port_sub = port.add_subparsers(dest="port_cmd", required=True)
    pi = port_sub.add_parser("install", help="build & install named ports")
    pi.add_argument("keys", nargs="+", metavar="PORT")
    _add_common(pi)
    pi.set_defaults(fn=cmd_port_install)
    port_sub.add_parser("list", help="list known ports and status"
                        ).set_defaults(fn=cmd_port_list)
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
