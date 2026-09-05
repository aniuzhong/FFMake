"""FFMake control plane.

  plan    derive the demanded closure for a triplet -> plans/<t>.plan.json
  build   construct every planned port (host tools first); stamps gate
  ffmpeg  patches + configure + make + install of the root product
  test    feature-gated smoke matrix (wine for PE triplets)
  dist    assemble the redistributable package (rpath relocation,
          manifest, checksums, archive)
  all     build -> ffmpeg -> test
"""

import argparse
import contextlib
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

from . import env as env_mod
from . import model
from . import paths
from . import plan as plan_mod
from . import validate
from .runners import get_runner
from .runners.base import run_with_heartbeat


def _die(msg):
    sys.exit("ffmake: " + str(msg))


def make_ctx(root, triplet, jobs=0, mkdirs=True):
    cfg = model.load_profile(root, triplet)
    if mkdirs:
        paths.ensure_workspace(root, triplet)
        paths.ensure_ascii_alias(root, triplet)
    return {
        "root": root,
        "triplet": triplet,
        "triplet_cfg": cfg,
        "prefix": paths.prefix(root, triplet),
        "tools_prefix": paths.tools_prefix(root),
        "pcdir": paths.sysroot_alias(root, triplet) + "/lib/pkgconfig",
        "logs": paths.logs(root),
        "jobs": jobs or os.cpu_count() or 4,
        "ffmpeg_src": None,
    }


def _system_tier(root, triplet):
    """Ports the host system satisfies on this triplet (declarative,
    generated once from the certified evidence by
    tools/gen_system_tier.py; maintained by hand afterwards)."""
    path = os.path.join(root, "profiles", "system-tier.json")
    if not os.path.isfile(path):
        return set()
    with open(path) as f:
        return set(json.load(f).get("triplets", {}).get(triplet, []))


def _load_channel(root, channel):
    path = os.path.join(root, "policy", channel + ".toml")
    if not os.path.isfile(path):
        _die("unknown channel '{}' ({} missing)".format(channel, path))
    import tomli
    with open(path, "rb") as f:
        return tomli.load(f)


def cmd_plan(args):
    root = paths.repo_root()
    uni = model.load_universe(root)
    cfg_path = plan_mod.configure_path(root)
    if not os.path.isfile(cfg_path):
        _die("ffmpeg source not seeded at {} -- seed the workspace or "
             "run 'upgrade'".format(cfg_path))
    p = plan_mod.compute(root, args.triplet, uni, cfg_path,
                         system_tier=_system_tier(root, args.triplet))
    path = plan_mod.write(root, args.channel, args.triplet, p)
    print("plan: {} [{}] -> {} ports (blocked {}, unmapped {})".format(
        args.triplet, args.channel, len(p["order"]), len(p["blocked"]),
        len(p["unmapped"])))
    print("plan: wrote {}".format(path))
    if p["blocked"]:
        print("plan: platform-blocked: {}".format(", ".join(p["blocked"])))


def cmd_build(args):
    root = paths.repo_root()
    uni = model.load_universe(root)
    if getattr(args, "from_plan", False):
        path = plan_mod.plan_path(root, args.channel, args.triplet)
        if not os.path.isfile(path):
            _die("no stored plan at {} -- run 'plan' or 'upgrade' "
                 "first".format(path))
        with open(path) as f:
            p = json.load(f)
        print("build: using stored plan ({} ports)".format(len(p["order"])))
    else:
        cfg_path = plan_mod.configure_path(root)
        if not os.path.isfile(cfg_path):
            _die("ffmpeg source not seeded at {} -- seed the workspace "
                 "first (cold) or fetch".format(cfg_path))
        p = plan_mod.compute(root, args.triplet, uni, cfg_path,
                             system_tier=_system_tier(root, args.triplet))
        plan_mod.write(root, args.channel, args.triplet, p)
    ctx = make_ctx(root, args.triplet, args.jobs)

    tools = [k for k, d in sorted(uni.items()) if d.get("tool")]
    for key in tools:
        _build_one(ctx, uni, key, args.triplet)
    ports = [k for k in p["order"] if k not in tools]
    if getattr(args, "parallel", False):
        _build_parallel(ctx, uni, ports, args.triplet, args.jobs)
    else:
        for key in ports:
            _build_one(ctx, uni, key, args.triplet)
    validate.closure_shlib_gate(ctx)
    print("build: closure complete ({} ports)".format(len(p["order"])))


def _build_one(ctx, uni, key, triplet):
    dep = uni[key]
    ov = dep.get("triplet_overrides", {}).get(triplet)
    if ov:
        # per-triplet port tweaks overlay before the runner sees the
        # recipe (the predecessor loop's _ensure_dep contract)
        dep = {**dep, **ov}
    runner = get_runner(dep.get("system", "makefile"), ctx)
    runner.build(key, dep)
    from . import fixup
    fixup.apply(ctx, key, dep)
    validate.validate_dep(ctx, key, dep)


def _build_layers(order, uni):
    """Topological levels: a port may start once every need has landed.
    Needs are declared knowledge; anything undeclared would be a race,
    which is exactly what this partition makes visible."""
    level = {}
    for key in order:
        needs = uni[key].get("needs", [])
        level[key] = 1 + max((level[n] for n in needs if n in level),
                             default=0)
    layers = {}
    for key in order:
        layers.setdefault(level[key], []).append(key)
    return [layers[i] for i in sorted(layers)]


def _build_parallel(ctx, uni, ports, triplet, jobs):
    from concurrent.futures import ThreadPoolExecutor
    from .runners.base import BuildError
    workers = max(1, jobs // 4)
    per_port = max(1, jobs // workers)
    print("build: parallel mode: {} workers x make -j{}".format(
        workers, per_port))
    for layer in _build_layers(ports, uni):
        lctx = dict(ctx)
        lctx["jobs"] = per_port
        errors = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_build_one, lctx, uni, key, triplet): key
                       for key in layer}
            for fut in futures:
                try:
                    fut.result()
                except Exception as e:  # noqa: BLE001 -- layer barrier
                    errors.append("{}: {}".format(futures[fut], e))
        if errors:
            raise BuildError("parallel layer failed:\n  " +
                             "\n  ".join(errors))


def _ensure_tools(ctx, uni, triplet):
    """Provision host tool ports (incl. binary-tier cross toolchains) on
    demand, so ffmpeg/dist verbs stay self-sufficient without a build."""
    for key, dep in sorted(uni.items()):
        if not dep.get("tool"):
            continue
        get_runner(dep.get("system", "makefile"), ctx).build(key, dep)


def _cuda_bin(flags):
    if "--enable-cuda-nvcc" in flags:
        return os.path.join(
            os.environ.get("CUDA_HOME", "/usr/local/cuda"), "bin")
    return None


def _cross_bin(ctx):
    tc = ctx["triplet_cfg"].get("cross_toolchain")
    return os.path.join(ctx["tools_prefix"], tc) if tc else None


def _apply_ffmpeg_patches(ctx):
    """Idempotent: dry-run forward -> apply; reverse -> already applied."""
    src = paths.ffmpeg_src_dir(ctx["root"])
    pdir = os.path.join(ctx["root"], "ports", "ffmpeg", "patches")
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


def cmd_ffmpeg(args):
    """configure + build + install the root product (seeded locked tree)."""
    root = paths.repo_root()
    uni = model.load_universe(root)
    ctx = make_ctx(root, args.triplet, args.jobs)
    _ensure_tools(ctx, uni, args.triplet)
    src = paths.ffmpeg_src_dir(root)
    if not os.path.isfile(os.path.join(src, "configure")):
        source = (uni.get("ffmpeg") or {}).get("source")
        if not source:
            _die("ffmpeg source missing and no ports/ffmpeg entry")
        get_runner("makefile", ctx).fetch_to(src, source, "ffmpeg")
    _apply_ffmpeg_patches(ctx)

    out = paths.ffmpeg_out(root, args.triplet)
    os.makedirs(out, exist_ok=True)
    flags = model.load_flags(root, args.triplet)
    base = [
        os.path.join(src, "configure"),
        "--prefix=" + ctx["prefix"],
        "--disable-doc",
        "--pkg-config=pkg-config",
        "--extra-cflags=-I" + os.path.join(ctx["prefix"], "include"),
        "--extra-ldflags=-L{lib} -Wl,-rpath,{lib}{dtags}".format(
            lib=os.path.join(ctx["prefix"], "lib"),
            dtags=" -Wl,--disable-new-dtags"
            if ctx["triplet_cfg"]["target_os"] == "linux" else ""),
    ] + ctx["triplet_cfg"]["ffmpeg_flags"]
    env = env_mod.build_child_env(
        ctx["prefix"],
        tools_bin=os.path.join(ctx["tools_prefix"], "bin"),
        prepend_path=_cuda_bin(flags),
        cross_bin=_cross_bin(ctx))

    log = os.path.join(ctx["logs"], "ffmpeg_configure.log")
    rc = run_with_heartbeat(base + flags, out, log, env=env,
                            label="ffmpeg configure")
    if rc != 0:
        _die("ffmpeg configure failed (see {})".format(log))
    print("ffmpeg: configure OK")

    log = os.path.join(ctx["logs"], "ffmpeg_make.log")
    rc = run_with_heartbeat(["make", "-j", str(ctx["jobs"])], out, log,
                            env=env, label="ffmpeg make")
    if rc != 0:
        _die("ffmpeg build failed (see {})".format(log))

    log = os.path.join(ctx["logs"], "ffmpeg_install.log")
    ienv = env_mod.build_child_env(
        ctx["prefix"], tools_bin=os.path.join(ctx["tools_prefix"], "bin"),
        cross_bin=_cross_bin(ctx))
    rc = run_with_heartbeat(["make", "install"], out, log, env=ienv,
                            label="ffmpeg install")
    if rc != 0:
        _die("ffmpeg install failed (see {})".format(log))
    _install_pe_runtime(ctx)
    print("ffmpeg: installed -> {}".format(ctx["prefix"]))


def _install_pe_runtime(ctx):
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
                print("ffmpeg: PE runtime {} -> bin/".format(
                    os.path.basename(src)))


def _ffmpeg_cmd(ctx):
    ffmpeg = os.path.join(ctx["prefix"], "bin",
                          ctx["triplet_cfg"]["exe"])
    if not os.path.isfile(ffmpeg):
        _die("installed ffmpeg not found at {} -- run the ffmpeg verb "
             "first".format(ffmpeg))
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
    from . import smoke
    root = paths.repo_root()
    ctx = make_ctx(root, args.triplet, args.jobs)
    env = env_mod.build_child_env(
        ctx["prefix"], tools_bin=os.path.join(ctx["tools_prefix"], "bin"))
    base = _ffmpeg_cmd(ctx)
    if base is None:
        print("test: SKIP ({} built, but wine not found)".format(
            ctx["triplet_cfg"]["exe"]))
        return 0
    enabled, version_line = _enabled_flags(base)
    print("test matrix ({}): {}".format(args.triplet, version_line))
    outdir = os.path.join(ctx["logs"], "smoke")
    os.makedirs(outdir, exist_ok=True)
    failed, ran = [], 0
    for case in smoke.load_cases(root):
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
                          "-vf", case["filter"], "-frames:v", "1", "-y",
                          out]
        elif case["kind"] == "decode":
            src = os.path.join(outdir, case["input_file"])
            if not os.path.isfile(src):
                print("  {:<18} SKIP   (input {} missing)".format(
                    name, case["input_file"]))
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
            print("  {:<18} FAIL   {}".format(name,
                                              r.stdout.strip()[:160]))
    for exe in ("ffmpeg", "ffprobe", "ffplay"):
        p = os.path.join(ctx["prefix"], "bin",
                         exe + ctx["triplet_cfg"]["exe"].replace("ffmpeg",
                                                                 ""))
        present = "PASS" if os.path.isfile(p) else "FAIL"
        if present == "FAIL":
            failed.append(exe)
        print("  {:<18} {}   {}".format("bin/" + exe, present,
                                        "" if present == "PASS" else p))
    cases = smoke.load_cases(root)
    print("summary: {} passed, {} failed, {} cases total".format(
        ran, len(failed), len(cases)))
    if failed:
        _die("smoke matrix failed: {}".format(", ".join(failed)))
    return 0


def _copy_filtered(src, dst, skip_ext=(".la",)):
    shutil.copytree(src, dst,
                    ignore=shutil.ignore_patterns(*["*" + e
                                                    for e in skip_ext]))


def _dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    return total


def cmd_dist(args):
    import tarfile
    import zipfile

    root = paths.repo_root()
    uni = model.load_universe(root)
    ctx = make_ctx(root, args.triplet, args.jobs)
    _ensure_tools(ctx, uni, args.triplet)
    prefix = ctx["prefix"]
    exe = os.path.join(prefix, "bin", ctx["triplet_cfg"]["exe"])
    if not os.path.isfile(exe):
        _die("no installed ffmpeg at {} -- run the ffmpeg verb "
             "first".format(exe))
    out_root = os.path.abspath(getattr(args, "out", None) or "store/releases")
    date = time.strftime("%Y%m%d")
    name = "ffmpeg-{}-{}".format(date, args.triplet)
    stage = os.path.join(out_root, name)
    if os.path.exists(stage):
        _die("release dir already exists: {}".format(stage))
    os.makedirs(stage)

    _copy_filtered(os.path.join(prefix, "bin"), os.path.join(stage, "bin"))
    _copy_filtered(os.path.join(prefix, "include"),
                   os.path.join(stage, "include"))
    _copy_filtered(os.path.join(prefix, "lib"), os.path.join(stage, "lib"))

    if ctx["triplet_cfg"]["target_os"] != "mingw32":
        patchelf = shutil.which("patchelf")
        if not patchelf:
            _die("patchelf not found -- required to relocate ELF rpaths")
        relocated = 0
        for sub in ("bin", "lib"):
            d = os.path.join(stage, sub)
            for dirpath, _, files in os.walk(d):
                for fn in files:
                    path = os.path.join(dirpath, fn)
                    try:
                        with open(path, "rb") as f:
                            if f.read(4) != b"\x7fELF":
                                continue
                    except OSError:
                        continue
                    os.chmod(path, 0o755)
                    subprocess.run(
                        [patchelf, "--set-rpath", "$ORIGIN/../lib",
                         "--force-rpath", path], check=True)
                    relocated += 1
        print("dist: relocated rpath on {} ELF files".format(relocated))

    base = _ffmpeg_cmd(ctx)
    version_lines, config_line = "", ""
    if base:
        r = subprocess.run(base + ["-hide_banner", "-version"],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, text=True)
        lines = r.stdout.splitlines()
        version_lines = "\n".join(lines[:2])
        for line in lines:
            if line.startswith("configuration:"):
                config_line = line
                break

    plan_path = os.path.join(root, "plans",
                             "%s.plan.json" % args.triplet)
    ports = "-"
    if os.path.isfile(plan_path):
        with open(plan_path) as f:
            ports = str(len(json.load(f)["order"]))

    mingw = ctx["triplet_cfg"]["target_os"] == "mingw32"
    manifest = "\n".join([
        "# {} release".format(name),
        "",
        "- generated: {}".format(time.strftime("%Y-%m-%d %H:%M %Z")),
        "- triplet: `{}` (target {})".format(
            args.triplet, ctx["triplet_cfg"]["target_os"]),
        "- version: {}".format(version_lines.splitlines()[0]
                               if version_lines else "unknown"),
        "- closure ports (plan): {}".format(ports),
        "",
        "## configuration",
        "",
        "    {}".format(config_line or "(unknown)"),
        "",
        "## verification",
        "",
        "SHA256SUMS covers every file in this tree:",
        "`sha256sum -c SHA256SUMS`",
        "",
    ])
    with open(os.path.join(stage, "MANIFEST.md"), "w") as f:
        f.write(manifest)

    sums = []
    for droot, _, files in os.walk(stage):
        for f in sorted(files):
            if f == "SHA256SUMS":
                continue
            p = os.path.join(droot, f)
            rel = os.path.relpath(p, stage)
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            sums.append("{}  {}".format(h.hexdigest(), rel))
    with open(os.path.join(stage, "SHA256SUMS"), "w") as f:
        f.write("\n".join(sums) + "\n")

    if mingw:
        arc = stage + ".zip"
        with zipfile.ZipFile(arc, "w", zipfile.ZIP_DEFLATED) as z:
            for droot, _, files in os.walk(stage):
                for f in sorted(files):
                    p = os.path.join(droot, f)
                    z.write(p, os.path.relpath(p, out_root))
    else:
        arc = stage + ".tar.xz"
        with tarfile.open(arc, "w:xz") as t:
            t.add(stage, arcname=name)
    print("dist: {} ({} MB tree, {} MB archive)".format(
        stage, _dir_size(stage) >> 20, os.path.getsize(arc) >> 20))


def _git_rev(src):
    r = subprocess.run(["git", "-C", src, "rev-parse", "HEAD"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       text=True)
    return r.stdout.strip() or None


def _plan_report(old, new):
    """Human-readable diff between two plans (the whole frontier that
    must move, in one glance -- the reason this verb exists)."""
    lo, ln = set(old["order"]), set(new["order"])
    lines = []
    if old.get("features") != new.get("features"):
        of, nf = set(old["features"]), set(new["features"])
        lines.append("  features: +{} -{}".format(
            sorted(nf - of), sorted(of - nf)))
    lines.append("  ports: {} -> {} (+{} -{})".format(
        len(lo), len(ln), sorted(ln - lo), sorted(lo - ln)))
    for label, key in (("unmapped", "unmapped"), ("blocked", "blocked")):
        ov, nv = old.get(key) or {}, new.get(key) or {}
        if ov != nv:
            lines.append("  {}: {} -> {}".format(label, ov, nv))
    return "\n".join(lines)


def _strip_ffmpeg_patches(src):
    """Reverse-apply every patch so the tree is checkout-clean. Patches
    live in ports/ffmpeg/patches and are re-applied idempotently by the
    ffmpeg verb after the new rev is checked out."""
    pdir = os.path.join(paths.repo_root(), "ports", "ffmpeg", "patches")
    if not os.path.isdir(pdir):
        return
    for name in sorted(os.listdir(pdir), reverse=True):
        if not name.endswith(".patch"):
            continue
        path = os.path.join(pdir, name)
        fwd = subprocess.run(["patch", "-d", src, "-p1", "--dry-run",
                              "-i", path], capture_output=True).returncode
        if fwd == 0:
            continue  # not applied
        subprocess.run(["patch", "-d", src, "-p1", "-R", "-i", path],
                       check=True, capture_output=True)
        print("upgrade: stripped patch {}".format(name))


def cmd_upgrade(args):
    """Channel-driven root refresh: fetch -> re-extract constraints ->
    replan -> diff report -> incremental build -> smoke."""
    import tomli
    root = paths.repo_root()
    uni = model.load_universe(root)
    ch = _load_channel(root, args.channel)
    target = args.to or ch["float"]["root"]
    src = paths.ffmpeg_src_dir(root)
    ctx = make_ctx(root, args.triplet, args.jobs)
    source = (uni.get("ffmpeg") or {}).get("source")
    if not os.path.isfile(os.path.join(src, "configure")):
        if not source:
            _die("ffmpeg source missing and no ports/ffmpeg entry")
        print("upgrade: fetching pinned ffmpeg seed")
        get_runner("makefile", ctx).fetch_to(src, source, "ffmpeg")

    old_rev = _git_rev(src)
    runner = get_runner("makefile", ctx)
    runner._run_net(
        ["git", "-C", src] + runner.GIT_SLOW + ["fetch", "origin", target],
        root, os.path.join(ctx["logs"], "ffmpeg_fetch.log"))
    _strip_ffmpeg_patches(src)
    subprocess.run(["git", "-C", src, "checkout", "-q", "FETCH_HEAD"],
                   check=True)
    new_rev = _git_rev(src)
    print("upgrade: ffmpeg {} -> {} (target {})".format(
        (old_rev or "?")[:12], new_rev[:12], target))

    plan_path = plan_mod.plan_path(root, args.channel, args.triplet)
    old_plan = None
    if os.path.isfile(plan_path):
        with open(plan_path) as f:
            old_plan = json.load(f)
    new_plan = plan_mod.compute(
        root, args.triplet, uni,
        plan_mod.configure_path(root),
        system_tier=_system_tier(root, args.triplet))
    if old_plan:
        print("upgrade: plan diff [{}]".format(args.triplet))
        print(_plan_report(old_plan, new_plan))
    else:
        print("upgrade: no prior plan; wrote fresh ({} ports)".format(
            len(new_plan["order"])))
    plan_mod.write(root, args.channel, args.triplet, new_plan)

    # version preflight: what the NEW configure demands vs what the
    # sysroot actually shipped (facts backfilled at validate time)
    from . import facts as facts_mod
    cons = facts_mod.extract_constraints(
        plan_mod.configure_path(root))
    facts_mod.write_constraints(root, new_rev, cons)
    checked, bad = facts_mod.preflight(root, args.triplet, cons)
    if checked:
        print("upgrade: version preflight: {} intervals checked".format(
            checked))
        for name, interval, ver in bad:
            print("upgrade: HINT {} would want {} (installed {}) -- "
                  "bump candidate; configure may still pass via an "
                  "alternative check path (the build decides)".format(
                      name, interval, ver))
    if args.plan_only:
        print("upgrade: plan-only, stopping before build")
        return 0

    cmd_build(args)
    cmd_ffmpeg(args)
    cmd_test(args)
    print("upgrade: OK ({} -> {})".format((old_rev or "?")[:12],
                                          new_rev[:12]))
    return 0


def cmd_canary(args):
    """Scheduled freshness probe: run upgrade, tee everything into a
    dated report, exit 0/1 so a cron job can alert. Failures are the
    product: they are the earliest signal that the knowledge base is
    drifting away from upstream."""
    root = paths.repo_root()
    os.makedirs(os.path.join(root, "workspace", "logs", "canary"),
                exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report = os.path.join(root, "workspace", "logs", "canary",
                          "{}-{}.md".format(stamp, args.triplet))

    class _Tee(object):
        def __init__(self, *files):
            self.files = files

        def write(self, s):
            for f in self.files:
                f.write(s)
            return len(s)

        def flush(self):
            for f in self.files:
                f.flush()

    verdict = "PASS"
    try:
        with open(report, "w") as f:
            with contextlib.redirect_stdout(_Tee(sys.stdout, f)):
                cmd_upgrade(args)
    except SystemExit as e:
        verdict = "FAIL (exit {})".format(e.code)
    except Exception as e:  # noqa: BLE001 -- canary must report, not die
        verdict = "FAIL ({}: {})".format(type(e).__name__, e)
    with open(report, "a") as f:
        f.write("\n## verdict: {}\n".format(verdict))
    print("canary: {} -- report {}".format(verdict, report))
    return 0 if verdict == "PASS" else 1


def cmd_all(args):
    cmd_build(args)
    cmd_ffmpeg(args)
    cmd_test(args)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    import json
    parser = argparse.ArgumentParser(prog="ffmake")
    sub = parser.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--triplet", default="linux-x86_64")
    common.add_argument("-j", "--jobs", type=int, default=0)
    common.add_argument("--channel", default="master",
                        help="policy channel (default: master)")
    for name, fn in (("plan", cmd_plan), ("build", cmd_build),
                     ("ffmpeg", cmd_ffmpeg), ("test", cmd_test),
                     ("dist", cmd_dist), ("all", cmd_all),
                     ("upgrade", cmd_upgrade), ("canary", cmd_canary)):
        sp = sub.add_parser(name, parents=[common])
        sp.set_defaults(fn=fn)
    sub.choices["build"].add_argument(
        "--from-plan", action="store_true",
        help="trust the stored plan instead of recomputing")
    sub.choices["build"].add_argument(
        "--parallel", action="store_true",
        help="build topological layers concurrently (needs must be "
             "fully declared)")
    for name in ("upgrade", "canary"):
        sub.choices[name].add_argument(
            "--to", default=None,
            help="override the channel's float target (rev/branch/tag)")
        sub.choices[name].add_argument(
            "--plan-only", action="store_true",
            help="fetch + replan + diff, stop before building")
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
