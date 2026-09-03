"""L4 driver: FFmpeg configure error-driven closed loop.

Loop: run FFmpeg's ./configure with the user's pass-through flags; when it
fails with "ERROR: <name> not found using pkg-config", look the name up in
deps.json, build that dep (runner), validate the install, and retry. Tool
deps ("tool": true) are bootstrapped before the first attempt so nasm etc.
are in PATH from the start. Unknown deps abort with an actionable message:
knowledge grows by adding entries, not by hiding failures.
"""

import json
import os
import re
import shlex
import subprocess
import sys

from . import env as env_mod
from . import fixups
from . import lock
from . import paths
from . import validate
from .runners import get_runner
from .runners.base import BuildError

# ffmpeg embeds version constraints in the message ("aom >= 2.0.0 not
# found ...") and pkg_config errors carry " using pkg-config" while
# check_lib/require errors do not -> capture the spec, first token = name
_ERROR_NOT_FOUND = re.compile(
    r"ERROR:\s+(.+?)\s+not found(?: using pkg-config)?")
# require() on a header/func pair word it as "X must be installed and
# version must be >= Y" when the compile/link probe fails
_ERROR_MUST_INSTALL = re.compile(
    r"ERROR:\s+(\S+)\s+must be installed")
# multi-check libs (libvpx) die with "X enabled but no supported ... found"
_ERROR_ENABLED_BUT = re.compile(
    r"^(\S+) enabled but", re.MULTILINE)
# multi-lib check (libcdio) words it as "No usable a/b found" — the spec
# is a slash-joined list of knowledge names
_ERROR_NO_USABLE = re.compile(
    r"ERROR: No usable (.+?) found")
# feature probes report unsatisfied deps as
# "X requested, but not all dependencies are satisfied: a, b"
_DEPS_UNSAT = re.compile(
    r"not all dependencies are satisfied: (.+)")
# one attempt discovers ONE missing port (ffmpeg configure fails fast on
# the first unsatisfied require) -> must exceed the closure size
_MAX_ATTEMPTS = 80


def _die(msg):
    sys.exit("ffmake: " + str(msg))


def _tail(path, n=30):
    try:
        with open(path, "r", errors="ignore") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except OSError:
        return "(log missing: {})".format(path)


def _load_deps(root):
    path = os.path.join(root, "deps.json")
    with open(path) as f:
        data = json.load(f)
    deps = data.get("deps", {})
    index = {}
    for key, dep in deps.items():
        for name in dep.get("match_names", [key]):
            index[name] = key
    return data, deps, index


def ensure_ffmpeg_src(ctx, ffmpeg_cfg):
    """Resolve the FFmpeg source tree, cloning the pinned rev if absent.

    Order (handled by cli._ctx): explicit --ffmpeg-src / env beats the
    workspace copy. Here we guarantee workspace/src/ffmpeg exists.
    """
    dst = paths.ffmpeg_src_dir(ctx["root"])
    if os.path.isfile(os.path.join(dst, "configure")):
        return dst
    source = (ffmpeg_cfg or {}).get("source")
    if not source:
        _die("FFmpeg source not found at {} and no 'ffmpeg' entry in "
             "deps.json to fetch it".format(dst))
    print("ffmpeg: fetching pinned source into {}".format(dst))
    try:
        get_runner("makefile", ctx).fetch_to(dst, source, "ffmpeg")
    except BuildError as e:
        _die(e)
    return dst


def apply_ffmpeg_patches(ctx):
    """Idempotently apply patches/ffmpeg/*.patch to the FFmpeg source tree.

    The workspace source persists across runs, so each patch is probed
    with a dry run first: clean forward -> apply; clean reverse ->
    already applied -> skip; anything else is a conflict and dies.
    """
    src = paths.ffmpeg_src_dir(ctx["root"])
    pdir = os.path.join(ctx["root"], "patches", "ffmpeg")
    if not os.path.isdir(pdir):
        return
    for name in sorted(os.listdir(pdir)):
        if not name.endswith(".patch"):
            continue
        path = os.path.join(pdir, name)
        fwd = subprocess.run(["patch", "-d", src, "-p1", "--dry-run",
                              "-i", path], capture_output=True).returncode
        if fwd == 0:
            subprocess.run(["patch", "-d", src, "-p1", "-i", path],
                           check=True, capture_output=True)
            print("ffmpeg: applied patch {}".format(name))
            continue
        rev = subprocess.run(["patch", "-d", src, "-p1", "--dry-run",
                              "-R", "-i", path],
                             capture_output=True).returncode
        if rev != 0:
            _die("ffmpeg patch '{}' does not apply and is not fully "
                 "applied (conflict?)".format(name))


def _read_flags(path):
    flags = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            flags.extend(shlex.split(line))
    return flags


def _run_logged(cmd, cwd, env, log_path):
    with open(log_path, "w") as f:
        return subprocess.run(cmd, cwd=cwd, env=env, stdout=f,
                              stderr=subprocess.STDOUT).returncode


def _ensure_dep(ctx, deps, key, _stack=()):
    """Build + validate a port, recursively building its "needs" first
    (deps-of-deps, e.g. dvdnav needs dvdread). Stamps make recursion cheap.
    """
    if key in _stack:
        _die("dependency cycle: {}".format(" -> ".join(_stack + (key,))))
    dep = deps[key]
    # per-triplet entry overrides (vcpkg-style port tweaks): deps.json
    # "triplet_overrides": {"<triplet>": {...fields to overlay...}}
    # merged BEFORE the needs walk so overrides can also declare per-triplet
    # needs (e.g. libzvbi only wants libiconv under mingw)
    ov = dep.get("triplet_overrides", {}).get(ctx["triplet"])
    if ov:
        dep = {**dep, **ov}
    for need in dep.get("needs", []):
        _ensure_dep(ctx, deps, need, _stack + (key,))
    runner = get_runner(dep.get("system", "makefile"), ctx)
    runner.build(key, dep)
    fixups.apply(ctx, key, dep)
    validate.validate_dep(ctx, key, dep)


def load_deps(root):
    """Public accessor: (full data, deps dict, ffmpeg-error-name index)."""
    data, deps, index = _load_deps(root)
    return data, deps, index


def build_dep(ctx, key):
    """Build + validate a single named port (used by `port install`)."""
    data, deps, index = _load_deps(ctx["root"])
    if key not in deps:
        _die("unknown port '{}' (known: {})".format(
            key, ", ".join(sorted(deps))))
    try:
        _ensure_dep(ctx, deps, key)
    except BuildError as e:
        _die(e)


def cuda_bin(flags):
    """nvcc bin dir when --enable-cuda-nvcc is requested (CUDA 12.8 layout)."""
    if "--enable-cuda-nvcc" in flags:
        return os.path.join(
            os.environ.get("CUDA_HOME", "/usr/local/cuda"), "bin")
    return None


def read_flags(root, triplet=None):
    """Public accessor: parsed ffmpeg_flags.txt as an argv list.

    Per-triplet file (ffmpeg_flags.<triplet>.txt) wins when present --
    cross triplets trim Linux-only flags there; the global file is the
    fallback shared by every triplet.
    """
    if triplet:
        per = os.path.join(root, "ffmpeg_flags.{}.txt".format(triplet))
        if os.path.isfile(per):
            return _read_flags(per)
    return _read_flags(os.path.join(root, "ffmpeg_flags.txt"))


def configure_loop(ctx):
    data, deps, index = _load_deps(ctx["root"])
    src = ctx.get("ffmpeg_src") or ensure_ffmpeg_src(ctx, data.get("ffmpeg"))
    apply_ffmpeg_patches(ctx)
    out = paths.ffmpeg_out(ctx["root"], ctx["triplet"])
    os.makedirs(out, exist_ok=True)
    log = os.path.join(ctx["logs"], "ffmpeg_configure.log")

    # Bootstrap host tools (nasm, ...) before anything needs them.
    for key, dep in sorted(deps.items()):
        if dep.get("tool"):
            _ensure_dep(ctx, deps, key)

    flags = read_flags(ctx["root"], ctx["triplet"])
    base = [
        os.path.join(src, "configure"),
        # FFmpeg's configure only accepts --opt=value joined form
        "--prefix=" + ctx["prefix"],
        "--disable-doc",
        # cross triplets prefix pkg-config with the cross prefix
        # (x86_64-w64-mingw32-pkg-config does not exist) -> use the host one;
        # our .pc files carry absolute sysroot paths, so this is safe
        "--pkg-config=pkg-config",
        "--extra-cflags=-I" + os.path.join(ctx["prefix"], "include"),
        # --disable-new-dtags keeps DT_RPATH (not RUNPATH): transitive
        # deps like libjxl_cms.so resolve from the sysroot RPATH.
        # ELF-only: mingw's PE ld rejects the option outright.
        "--extra-ldflags=-L{lib} -Wl,-rpath,{lib}{dtags}".format(
            lib=os.path.join(ctx["prefix"], "lib"),
            dtags=" -Wl,--disable-new-dtags"
            if ctx["triplet_cfg"]["target_os"] == "linux" else ""),
    ] + ctx["triplet_cfg"]["ffmpeg_flags"]
    _tc = ctx["triplet_cfg"].get("cross_toolchain")
    env = env_mod.build_child_env(
        ctx["prefix"],  # prefix-first: system .pc ok
        tools_bin=os.path.join(ctx["tools_prefix"], "bin"),
        # --enable-cuda-nvcc builds PTX via nvcc; it is not in the
        # narrowed system PATH, so prepend the CUDA toolkit bin dir
        prepend_path=cuda_bin(flags),
        # triplet's cross toolchain (e.g. llvm-mingw) beats the distro's
        cross_bin=os.path.join(ctx["tools_prefix"], _tc) if _tc else None)

    built = []
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        print("configure: attempt {} ...".format(attempt))
        rc = _run_logged(base + flags, out, env, log)
        if rc == 0:
            ctx["flags"] = flags
            try:
                lock.write_lock(ctx, data, deps, built)
            except OSError as e:
                print("lock: write failed ({})".format(e))
            print("configure: OK (closure built this run: {})".format(
                ", ".join(built) if built else "nothing was missing"))
            return built
        with open(log, "r", errors="ignore") as f:
            text = f.read()
        missing = [spec.split()[0]
                   for spec in _ERROR_NOT_FOUND.findall(text)]
        missing += [name for name in _ERROR_MUST_INSTALL.findall(text)]
        missing += [name for name in _ERROR_ENABLED_BUT.findall(text)]
        for spec in _ERROR_NO_USABLE.findall(text):
            for name in spec.split("/"):
                name = name.strip()
                if name:
                    missing.append(name)
        for spec in _DEPS_UNSAT.findall(text):
            for name in spec.split(","):
                name = name.strip()
                if name:
                    missing.append(name)
        if not missing:
            _die("configure failed with unknown error; log tail:\n" +
                 _tail(log))
        print("configure: unsatisfied after checks: {}".format(
            ", ".join(sorted(missing))))
        print(_tail(log))
        for name in missing:
            key = index.get(name)
            if not key:
                _die("dependency '{}' is not in deps.json; "
                     "add a knowledge entry for it".format(name))
            plat = deps[key].get("platforms")
            if plat:
                # platforms supports two syntaxes: exact triples (e.g., 'linux-x86_64') or
                # family labels (e.g., 'linux'). A full-string comparison would prevent family
                # labels from ever matching
                # —— during cold builds, all family-label ports without stamp info were
                # incorrectly blocked (lesson: the error message itself says "covers linux only",
                # but the implementation did a literal string comparison)
                fam = ctx["triplet"].split("-")[0]
                if ctx["triplet"] not in plat and fam not in plat:
                    _die("port '{}' covers {} only, but triplet '{}' "
                         "requested it; trim the requesting flag from this "
                         "triplet's flags file".format(
                             key, "/".join(plat), ctx["triplet"]))
            if key not in built:
                print("configure: missing '{}' -> building dep '{}'".format(
                    name, key))
                try:
                    _ensure_dep(ctx, deps, key)
                except BuildError as e:
                    _die(e)
                built.append(key)
    _die("configure did not converge within {} attempts".format(
        _MAX_ATTEMPTS))
