"""Command-line entry of ffmake (CMake-aligned lifecycle verbs).

  configure  Pass through FFmpeg configure flags; build missing deps via
             the error-driven loop until configure succeeds.
  build      Compile FFmpeg in the per-triplet out-of-tree build dir.
  install    Install FFmpeg into the per-triplet sysroot.
  test       Smoke-test the installed binaries (wine for cross triplets).
  all        Chain configure -> build -> install -> test.
  port       vcpkg-style dependency management: install <key>..., list.

Non-lifecycle: probe (L0 diagnostics), init (optional workspace bootstrap).
Triplets: linux-x86_64 (native), mingw-x86_64-llvm (cross).
"""

import argparse
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

from . import env as env_mod
from . import loop
from . import paths
from . import smoke
from . import toolchains
from . import triplets as triplets_mod
from . import validate


def _die(msg):
    sys.exit("ffmake: " + str(msg))


def _ctx(args):
    root = paths.repo_root()
    paths.ensure_workspace(root, args.triplet)
    # ASCII alias symlinks + pkg-config wrapper (non-ASCII repo path guard)
    paths.ensure_ascii_alias(root, args.triplet)
    triplet_cfg = triplets_mod.get(args.triplet)
    # host toolchains (llvm-mingw ...) provision on demand, pinned by
    # toolchains.json — before any verb touches the triplet
    toolchains.ensure(root, triplet_cfg)
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
        "triplet": args.triplet,
        "triplet_cfg": triplet_cfg,
        "prefix": paths.prefix(root, args.triplet),
        "tools_prefix": paths.tools_prefix(root),
        "pcdir": paths.sysroot_alias(root, args.triplet) + "/lib/pkgconfig",
        "logs": paths.logs(root),
        "jobs": args.jobs or os.cpu_count() or 4,
        "ffmpeg_src": src,
    }


def cmd_configure(args):
    loop.configure_loop(_ctx(args))


def _cross_bin(ctx):
    tc = ctx["triplet_cfg"].get("cross_toolchain")
    if not tc:
        return None
    return os.path.join(ctx["tools_prefix"], tc)


def cmd_build(args):
    ctx = _ctx(args)
    out = paths.ffmpeg_out(ctx["root"], ctx["triplet"])
    if not os.path.exists(os.path.join(out, "ffbuild", "config.mak")):
        _die("no configuration in {} -- run 'configure' first".format(out))
    log = os.path.join(ctx["logs"], "ffmpeg_make.log")
    # L0 env is mandatory for every subprocess: PATH must prefer the
    # host tools (nasm) over any system toolchain. cuda_bin keeps nvcc
    # reachable for --enable-cuda-nvcc PTX builds; cross_bin resolves the
    # triplet's cross toolchain ahead of the distro one.
    env = env_mod.build_child_env(
        ctx["prefix"], tools_bin=os.path.join(ctx["tools_prefix"], "bin"),
        prepend_path=loop.cuda_bin(loop.read_flags(
            ctx["root"], ctx["triplet"])),
        cross_bin=_cross_bin(ctx))
    with open(log, "w") as f:
        pass
    from .runners.base import run_with_heartbeat
    rc = run_with_heartbeat(["make", "-j", str(ctx["jobs"])], cwd=out,
                            log_path=log, env=env, label="ffmpeg make")
    if rc != 0:
        _die("build failed (see {})".format(log))
    print("build: OK")


def cmd_install(args):
    ctx = _ctx(args)
    out = paths.ffmpeg_out(ctx["root"], ctx["triplet"])
    log = os.path.join(ctx["logs"], "ffmpeg_install.log")
    env = env_mod.build_child_env(
        ctx["prefix"], tools_bin=os.path.join(ctx["tools_prefix"], "bin"),
        cross_bin=_cross_bin(ctx))
    from .runners.base import run_with_heartbeat
    rc = run_with_heartbeat(["make", "install"], cwd=out,
                            log_path=log, env=env, label="ffmpeg install")
    if rc != 0:
        _die("install failed (see {})".format(log))
    _install_pe_runtime(ctx)
    print("install: OK -> {}".format(ctx["prefix"]))


def _install_pe_runtime(ctx):
    """Ship the toolchain's PE runtime DLLs next to the binaries.

    Cross-built binaries dynamically link the toolchain runtime
    (winpthread/gcc_seh/stdc++/gomp for the gcc triplet, libc++/unwind/
    winpthread/libomp for llvm-mingw); a sysroot without them runs
    nowhere -- neither under wine nor on real Windows. The triplet
    table declares what to copy ([name-or-glob, src_dir] pairs, where
    "TOOLS:" marks a path relative to the shared tools sysroot).
    Idempotent.
    """
    entries = ctx["triplet_cfg"].get("pe_runtime")
    if not entries:
        return
    bindir = os.path.join(ctx["prefix"], "bin")
    for name, src_dir in entries:
        if src_dir.startswith("TOOLS:"):
            src_dir = os.path.join(ctx["tools_prefix"],
                                   src_dir[len("TOOLS:"):])
        for src in glob.glob(os.path.join(src_dir, name)):
            dst = os.path.join(bindir, os.path.basename(src))
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
                print("install: PE runtime {} -> bin/".format(
                    os.path.basename(src)))


def _ffmpeg_cmd(ctx):
    """Base command for running the installed ffmpeg (wine for PE triplets)."""
    ffmpeg = os.path.join(ctx["prefix"], "bin", ctx["triplet_cfg"]["exe"])
    if not os.path.isfile(ffmpeg):
        _die("installed ffmpeg not found at {} -- run 'install' first"
             .format(ffmpeg))
    cmd = [ffmpeg]
    if ctx["triplet_cfg"]["target_os"] == "mingw32":
        wine = shutil.which("wine64") or shutil.which("wine")
        if not wine:
            return None
        cmd = [wine, ffmpeg]
    return cmd


def _enabled_flags(env_cmd):
    r = subprocess.run(env_cmd + ["-hide_banner", "-version"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       text=True)
    first = r.stdout.splitlines()[0] if r.stdout else ""
    for line in r.stdout.splitlines():
        if line.startswith("configuration:"):
            return set(line.split()), first
    return set(), first


def cmd_test(args):
    ctx = _ctx(args)
    env = env_mod.build_child_env(
        ctx["prefix"], tools_bin=os.path.join(ctx["tools_prefix"], "bin"))
    base = _ffmpeg_cmd(ctx)
    if base is None:
        print("test: SKIP ({} built, but wine not found to run it)"
              .format(ctx["triplet_cfg"]["exe"]))
        return 0

    enabled, version_line = _enabled_flags(base)
    print("test matrix ({}): {}".format(ctx["triplet"], version_line))

    outdir = os.path.join(ctx["logs"], "smoke")
    os.makedirs(outdir, exist_ok=True)
    failed = []
    ran = 0
    for case in smoke.CASES:
        name = case["name"]
        if case["flag"] not in enabled:
            print("  {:<18} SKIP   ({} not enabled)".format(name,
                                                            case["flag"]))
            continue
        out = os.path.join(outdir, name + "." + case.get("ext", "log"))
        stream = case.get("stream", "v")
        if case["kind"] == "encode":
            cmd = base + ["-hide_banner", "-loglevel", "error",
                          "-f", "lavfi", "-i", case["input"],
                          "-c:" + stream, case["encoder"], "-y", out]
        elif case["kind"] == "filter":
            cmd = base + ["-hide_banner", "-loglevel", "error",
                          "-f", "lavfi", "-i", case["input"],
                          "-vf", case["filter"], "-frames:v", "1", "-y", out]
        elif case["kind"] == "decode":
            # input produced by an earlier case in the matrix; the
            # decoder is an INPUT option (forced before demuxing)
            src = os.path.join(outdir, case["input_file"])
            if not os.path.isfile(src):
                print("  {:<18} SKIP   (input {} missing)".format(name,
                                                                  case[
                                                                      "input_file"]))
                continue
            cmd = base + ["-hide_banner", "-loglevel", "error",
                          "-c:v", case["decoder"], "-i", src,
                          "-f", "null", "-"]
        elif case["kind"] == "capability":
            cmd = base + ["-hide_banner", "-" + case["list"]]
        else:
            _die("unknown smoke kind: " + case["kind"])
        r = subprocess.run(cmd, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True)
        ok = r.returncode == 0
        detail = ""
        if case["kind"] == "capability":
            ok = ok and case["needle"] in r.stdout
            detail = "listed in -{}".format(case["list"])
        elif ok and case["kind"] == "decode":
            detail = "stream decoded to null"
        elif ok and os.path.isfile(out):
            detail = "{} bytes".format(os.path.getsize(out))
        if ok:
            ran += 1
            print("  {:<18} PASS   {}".format(name, detail))
        else:
            failed.append(name)
            print("  {:<18} FAIL   {}" .format(name, r.stdout.strip()[:160]))

    # binary inventory
    for exe in ("ffmpeg", "ffprobe", "ffplay"):
        p = os.path.join(ctx["prefix"], "bin",
                         exe + ctx["triplet_cfg"]["exe"].replace("ffmpeg", ""))
        present = "PASS" if os.path.isfile(p) else "FAIL"
        if present == "FAIL":
            failed.append(exe)
        print("  {:<18} {}   {}".format("bin/" + exe, present,
                                        "" if present == "PASS" else p))

    print("summary: {} passed, {} failed, {} cases total".format(
        ran, len(failed), len(smoke.CASES)))
    if failed:
        _die("smoke matrix failed: {}".format(", ".join(failed)))
    return 0


def cmd_all(args):
    cmd_configure(args)
    cmd_build(args)
    cmd_install(args)
    cmd_test(args)


def _copy_filtered(src, dst, skip_ext=(".la",)):
    """copytree that drops libtool .la files (they embed absolute
    build-tree paths and are useless to consumers)."""
    shutil.copytree(src, dst,
                    ignore=shutil.ignore_patterns(*["*" + e for e in
                                                    skip_ext]))


def _dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    return total


def cmd_dist(args):
    import tarfile
    import zipfile

    ctx = _ctx(args)
    prefix = ctx["prefix"]
    exe = os.path.join(prefix, "bin", ctx["triplet_cfg"]["exe"])
    if not os.path.isfile(exe):
        _die("no installed ffmpeg at {} -- run 'install' first".format(exe))

    out_root = os.path.abspath(getattr(args, "out", None) or "release")
    date = time.strftime("%Y%m%d")
    name = "ffmpeg-{}-{}".format(date, ctx["triplet"])
    stage = os.path.join(out_root, name)
    if os.path.exists(stage):
        _die("release dir already exists: {}".format(stage))
    os.makedirs(stage)

    # runtime: fftools + co-located DLLs/shared libs (PE loaders resolve
    # imports from the exe directory; keep bin/ together)
    _copy_filtered(os.path.join(prefix, "bin"), os.path.join(stage, "bin"))
    # dev: headers + import/static archives + pkgconfig + cmake configs
    _copy_filtered(os.path.join(prefix, "include"),
                   os.path.join(stage, "include"))
    _copy_filtered(os.path.join(prefix, "lib"), os.path.join(stage, "lib"))

    # linkage relocation (ELF triplets): the build tree carries an absolute
    # DT_RPATH into the workspace sysroot (loop.py sets it on purpose for
    # transitive deps-of-deps resolution). Shipped that way, the package
    # only runs on the build machine. Rewrite to $ORIGIN/../lib so bin/ and
    # lib/ travel together; --force-rpath keeps DT_RPATH (not RUNPATH) so
    # transitive resolution still works (the libjxl_cms lesson).
    if ctx["triplet_cfg"]["target_os"] != "mingw32":
        patchelf = shutil.which("patchelf")
        if not patchelf:
            _die("patchelf not found -- required to relocate ELF rpaths; "
                 "install it (image helper-tools layer) or dist on the "
                 "build image")
        relocated = 0
        for sub in ("bin", "lib"):
            root = os.path.join(stage, sub)
            for dirpath, _, files in os.walk(root):
                for fn in files:
                    path = os.path.join(dirpath, fn)
                    try:
                        with open(path, "rb") as f:
                            if f.read(4) != b"\x7fELF":
                                continue
                    except OSError:
                        continue
                    subprocess.run(
                        [patchelf, "--set-rpath", "$ORIGIN/../lib",
                         "--force-rpath", path], check=True)
                    relocated += 1
        print("dist: relocated rpath on {} ELF files".format(relocated))

    # version banner (run the real binary; wine for PE triplets)
    base = _ffmpeg_cmd(ctx)
    version_lines, config_line = "", ""
    if base:
        r = subprocess.run(base + ["-hide_banner", "-version"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True)
        lines = r.stdout.splitlines()
        version_lines = "\n".join(lines[:2])
        for line in lines:
            if line.startswith("configuration:"):
                config_line = line
                break

    # lock summary
    lock_ports = "-"
    lock_path = os.path.join(ctx["root"], "lock.json")
    if os.path.isfile(lock_path):
        with open(lock_path) as f:
            lk = json.load(f)
        section = lk.get("triplets", {}).get(ctx["triplet"])
        if section is not None:
            lock_ports = str(len(section.get("ports", section)))

    mingw = ctx["triplet_cfg"]["target_os"] == "mingw32"
    reloc = ("Windows: keep bin/ together (PE DLL search is exe-relative)."
             if mingw else
             "Linux: ELF rpaths rewritten to $ORIGIN/../lib — the tree is "
             "relocatable; run from anywhere.")
    manifest = "\n".join([
        "# {} release".format(name),
        "",
        "- generated: {}".format(time.strftime("%Y-%m-%d %H:%M %Z")),
        "- triplet: `{}` (target {})".format(ctx["triplet"],
                                             ctx["triplet_cfg"]["target_os"]),
        "- version: {}".format(version_lines.splitlines()[0]
                               if version_lines else "unknown"),
        "- built with: {}".format(
            version_lines.splitlines()[1][len("built with "):]
            if len(version_lines.splitlines()) > 1
            and version_lines.splitlines()[1].startswith("built with ")
            else "unknown"),
        "- closure ports (lock.json): {}".format(lock_ports),
        "- relocatability: {}".format(reloc),
        "",
        "## configuration",
        "",
        "    {}".format(config_line or "(unknown)"),
        "",
        "## layout",
        "",
        "- `bin/`   -- fftools + runtime libraries (keep together)",
        "- `include/` -- ffmpeg and dependency headers",
        "- `lib/`   -- import/static archives + pkgconfig + cmake configs"
        + (" (MinGW COFF import libs `.dll.a`; MSVC-compatible for C APIs)"
           if mingw else ""),
        "",
        "## verification",
        "",
        "SHA256SUMS covers every file in this tree:",
        "`sha256sum -c SHA256SUMS`",
        "",
    ])
    with open(os.path.join(stage, "MANIFEST.md"), "w") as f:
        f.write(manifest)

    # checksums
    sums = []
    for root, _, files in os.walk(stage):
        for f in sorted(files):
            if f == "SHA256SUMS":
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, stage)
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            sums.append("{}  {}".format(h.hexdigest(), rel))
    with open(os.path.join(stage, "SHA256SUMS"), "w") as f:
        f.write("\n".join(sums) + "\n")

    # archive
    if mingw:
        arc = stage + ".zip"
        with zipfile.ZipFile(arc, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(stage):
                for f in sorted(files):
                    p = os.path.join(root, f)
                    z.write(p, os.path.relpath(p, out_root))
    else:
        arc = stage + ".tar.xz"
        with tarfile.open(arc, "w:xz") as t:
            t.add(stage, arcname=name)

    print("dist: {} ({} MB tree, {} MB archive)".format(
        stage, _dir_size(stage) >> 20,
        os.path.getsize(arc) >> 20))
    print("dist: archive {}".format(arc))


def cmd_port_install(args):
    ctx = _ctx(args)
    for key in args.keys:
        loop.build_dep(ctx, key)


def cmd_port_list(_args):
    root = paths.repo_root()
    paths.ensure_workspace(root)
    paths.ensure_ascii_alias(root, triplets_mod.DEFAULT)
    data, deps, index = loop.load_deps(root)
    prefix = paths.prefix(root, triplets_mod.DEFAULT)
    tools_prefix = paths.tools_prefix(root)
    print("{:<12} {:<10} {:<10} {}".format(
        "PORT", "SYSTEM", "STATUS", "SOURCE"))
    for key, dep in sorted(deps.items()):
        status = "installed" if validate.is_installed(
            prefix, tools_prefix, key, dep) else "missing"
        source = dep.get("source") or {}
        where = source.get("rev") or source.get("url") or ""
        print("{:<12} {:<10} {:<10} {}".format(
            key, dep.get("system", "-"), status, where))


# --- backup / restore: snapshot everything expensive to rebuild ----------
# Kept: distfiles (offline re-fetch), stamps (ABI-hash validity state),
# out/ (installed sysroots = the actual build products), lock.json and the
# two declarative inputs. Skipped: src/, build/, logs/, tools/ (all
# regenerable; tools rebuild in minutes from warm bootstrap).

def _backup_members(root):
    members = [
        os.path.join("workspace", "distfiles"),
        os.path.join("workspace", "var", "stamps"),
        os.path.join("workspace", "out"),
        os.path.join("workspace", ".gitkeep"),
    ]
    for f in ("deps.json", "ffmpeg_flags.txt", "lock.json"):
        if os.path.isfile(os.path.join(root, f)):
            members.append(f)
    return [m for m in members if os.path.exists(os.path.join(root, m))]


def cmd_backup(args):
    root = paths.repo_root()
    paths.ensure_workspace(root)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = os.path.abspath(args.output.replace("{stamp}", stamp))
    members = _backup_members(root)
    tmp = out + ".tmp"
    cmd = ["tar", "czf", tmp, "-C", root] + members
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        _die("backup failed (tar rc={})".format(rc))
    os.replace(tmp, out)
    print("backup: OK -> {} ({})".format(
        out, _human(os.path.getsize(out))))


def cmd_restore(args):
    root = paths.repo_root()
    paths.ensure_workspace(root)
    src = os.path.abspath(args.archive)
    if not os.path.isfile(src):
        _die("backup not found: {}".format(src))
    rc = subprocess.run(["tar", "xzf", src, "-C", root]).returncode
    if rc != 0:
        _die("restore failed (tar rc={})".format(rc))
    print("restore: OK from {} -- run 'ffmake all' to resume".format(src))


def _human(n):
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024:
            return "{:.1f} {}".format(n, unit)
        n /= 1024.0
    return "{:.1f} TiB".format(n)


def cmd_probe(_args):
    prefix = paths.prefix(paths.repo_root(), triplets_mod.DEFAULT)

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

    # 4) Declared host toolchains (provisioned on demand by build verbs).
    toolchains.report(paths.repo_root())

    # 5) Host tool expectations that recipes assume implicitly; missing
    #    entries warn (provisioning differs per environment) instead of
    #    failing — the build verbs surface hard errors with context.
    cargo_bin = os.path.join(os.path.expanduser("~"), ".cargo", "bin")
    expectations = [
        ("cargo", os.path.join(cargo_bin, "cargo"),
         "librav1e build"),
        ("cbindgen", os.path.join(cargo_bin, "cbindgen"),
         "librav1e headers"),
        ("patchelf", None, "dist rpath relocation"),
        ("wine", None, "mingw smoke tests + cmake try_run"),
        ("nvcc", None, "CUDA_HOME (linux --enable-cuda-nvcc)"),
    ]
    for tool, path_hint, why in expectations:
        path = path_hint or shutil.which(tool)
        ok = bool(path) and os.path.exists(path)
        print("host tool {:<10} {:<7} {}".format(
            tool, "ok" if ok else "MISSING", why))


def cmd_init(_args):
    root = paths.repo_root()
    ws = paths.ensure_workspace(root)
    print("workspace: {}".format(ws))


def _add_common(p):
    p.add_argument("--ffmpeg-src", default=None,
                   help="FFmpeg source tree (default: $FFMAKE_FFMPEG_SRC "
                        "or workspace/src/ffmpeg, auto-cloned)")
    p.add_argument("-j", "--jobs", type=int, default=0,
                   help="parallel jobs (default: cpu count)")
    p.add_argument("--triplet", default=triplets_mod.DEFAULT,
                   choices=sorted(triplets_mod.TRIPLETS),
                   help="target triplet (default: {})".format(
                       triplets_mod.DEFAULT))


def _make_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(sys.argv[0]) or "ffmake.py",
        description="Full-source FFmpeg build system "
                    "(CMake-aligned lifecycle verbs, vcpkg-style triplets)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name, help_, fn in (
        ("configure",
         "build missing deps (error-driven loop) and make FFmpeg's "
         "configure pass", cmd_configure),
        ("build", "compile FFmpeg out-of-tree", cmd_build),
        ("install", "install FFmpeg into the per-triplet sysroot",
         cmd_install),
        ("test", "smoke-test the installed binaries", cmd_test),
        ("all", "configure -> build -> install -> test", cmd_all),
        ("dist", "assemble a redistributable package "
                 "(bin + dev + manifest)", cmd_dist),
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
    pl = port_sub.add_parser("list", help="list known ports and status")
    _add_common(pl)
    pl.set_defaults(fn=cmd_port_list)

    # snapshot/restore of everything expensive to rebuild (vcpkg binary
    # caching analog, archive form): distfiles + stamps + out/ + lock
    bk = sub.add_parser("backup", help="snapshot distfiles+stamps+out")
    bk.add_argument("-o", "--output", default="ffmake-backup-{stamp}.tar.gz",
                    metavar="FILE")
    bk.set_defaults(fn=cmd_backup)
    rs = sub.add_parser("restore", help="restore a backup archive")
    rs.add_argument("archive", metavar="FILE")
    rs.set_defaults(fn=cmd_restore)
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
