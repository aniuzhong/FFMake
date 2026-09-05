"""L1 runner base: fetching, stamps, logging, child env.

vcpkg-inspired layout mapping:
  downloads/   <-> workspace/distfiles/       (tarball + tool bootstrap cache)
  buildtrees/  <-> workspace/build/<ns>/<key>/ (per-port out-of-tree build + logs)
  installed/<triplet> <-> workspace/out/<triplet>/ (per-triplet sysroot)
  host tools   <-> workspace/tools/           (shared by all triplets)
  ports/<port>/{vcpkg.json,portfile} <-> deps.json entry + runner class
  packages/<port>_<triplet>/ staging <-> validate.py gate (fixups land in phase 2)

Stamp semantics: JSON {hash, rev, url, args}, namespaced per triplet (or
"tools" for host tools).
  - hash (recipe_version + rev + args) matches -> skip entirely
  - rev/url unchanged, args changed -> keep pristine src/, wipe build dir
  - rev/url changed -> wipe src/ and build dir, re-fetch
"""

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.parse

from .. import env as env_mod
from .. import paths

# Bump to invalidate all stamps after recipe changes.
RECIPE_VERSION = 3

# User-provided local proxy; used as fallback when a network step fails.
FALLBACK_PROXY = "http://127.0.0.1:10808"


class BuildError(Exception):
    pass


def _proxy_reachable(proxy_url, timeout=1.5):
    """True if the fallback proxy actually listens — prevents pointless
    proxy retries in proxy-free environments (GH runners), where the
    unconditional retry used to just duplicate the failure."""
    import socket
    try:
        parsed = urllib.parse.urlparse(proxy_url)
        with socket.create_connection(
                (parsed.hostname, parsed.port or 80), timeout=timeout):
            return True
    except OSError:
        return False


def run_with_heartbeat(cmd, cwd, log_path, env=None, label=None,
                       interval=None):
    """Run with stdout/stderr redirected into log_path. A daemon thread
    prints a heartbeat line every interval so CI pages show liveness
    during long compiles (stdout is the only thing CI streams)."""
    if interval is None:
        interval = int(os.environ.get("FFMAKE_HEARTBEAT_SECS", "120"))
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    label = label or cmd[0]
    with open(log_path, "w") as f:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env,
                                stdout=f, stderr=subprocess.STDOUT)
        start = time.monotonic()

        def _beat():
            while proc.poll() is None:
                time.sleep(interval)
                if proc.poll() is None:
                    print("{}: still running ({}s elapsed)".format(
                        label, int(time.monotonic() - start)), flush=True)

        threading.Thread(target=_beat, daemon=True).start()
        return proc.wait()


def _log_tail(path, lines=40, window=16384):
    """Last `lines` of a build log, read from a bounded tail window so
    multi-MB logs stay cheap. Prefixed for visual separation in stdout."""
    try:
        with open(path, "r", errors="ignore") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - window))
            chunk = f.read()
        body = "\n".join("    | " + l
                         for l in chunk.splitlines()[-lines:])
        return "    (log tail: {})\n{}".format(path, body)
    except OSError:
        return "    (log unavailable: {})".format(path)


class Runner(object):
    system = "base"

    def __init__(self, ctx):
        self.ctx = ctx

    def ns(self, dep):
        """Stamps/build trees are namespaced: host tools vs per-triplet."""
        return paths.TOOLS_NS if dep.get("tool") else self.ctx["triplet"]

    def install_prefix(self, dep):
        """Host tools install to the shared tools sysroot; everything
        else installs into the per-triplet sysroot."""
        return self.ctx["tools_prefix"] if dep.get("tool") \
            else self.ctx["prefix"]

    def cross_bin(self):
        """Cross toolchain bin dir for this triplet (None for native)."""
        sub = self.ctx["triplet_cfg"].get("cross_toolchain")
        if not sub:
            return None
        return os.path.join(self.ctx["tools_prefix"], sub)

    def env(self, strict=True, extra=None, cross=True):
        # PKG_CONFIG traffic goes through the ASCII alias pcdir so that
        # meson/cmake consumers never see non-ASCII sysroot paths.
        # cross=False is for host tools (dep["tool"]): their binaries run
        # on the build machine, so the cross toolchain must stay out of
        # PATH — a cross cc earlier than /usr/bin would turn a host tool
        # into a target binary (the nasm.exe lesson).
        return env_mod.build_child_env(
            self.ctx["prefix"], strict_pkgconfig=strict,
            tools_bin=os.path.join(self.ctx["tools_prefix"], "bin"),
            cross_bin=self.cross_bin() if cross else None,
            pcdir=self.ctx.get("pcdir"), extra=extra)

    def run(self, cmd, cwd, log_path, env=None):
        log_dir = os.path.dirname(log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        # env=None must NOT leak the parent process PATH/proxy vars into
        # build steps -- default to the L0-scrubbed engine environment
        rc = run_with_heartbeat(cmd, cwd, log_path,
                                env if env is not None else self.env())
        if rc != 0:
            # CI run pages stream stdout only -- tail the log so a
            # failure is diagnosable without the (ephemeral) log file.
            print("{} failed in {} (exit {})".format(cmd[0], cwd, rc))
            print(_log_tail(log_path))
            raise BuildError("{} failed in {} (see {})".format(
                cmd[0], cwd, log_path))

    def cross_file(self, kind, bdir):
        """Emit a CMake toolchain file ("cmake") or Meson cross file ("meson")
        for the current triplet into bdir; None for the native triplet.

        The triplet table declares the target; the runners generate the
        per-build-system plumbing from it (vcpkg toolchain-file analog).
        pkg-config stays the host binary: our .pc files carry absolute
        sysroot paths, and PKG_CONFIG_LIBDIR already pins the target
        sysroot via the L0 env.
        """
        cfg = self.ctx["triplet_cfg"]
        if not cfg.get("cross_prefix"):
            return None
        xp = cfg["cross_prefix"]
        cc_sfx = cfg.get("cc_suffix", "")
        header = "# generated by ffmake from triplet '{}': do not edit".format(
            self.ctx["triplet"])
        if kind == "cmake":
            path = os.path.join(bdir, "cross-toolchain.cmake")
            body = "\n".join([
                header,
                "set(CMAKE_SYSTEM_NAME {})".format(cfg["cmake_system_name"]),
                "set(CMAKE_SYSTEM_PROCESSOR {})".format(
                    cfg["cmake_system_processor"]),
                "set(CMAKE_C_COMPILER {}gcc{})".format(xp, cc_sfx),
                "set(CMAKE_CXX_COMPILER {}g++{})".format(xp, cc_sfx),
                "set(CMAKE_RC_COMPILER {}windres)".format(xp),
                "set(CMAKE_FIND_ROOT_PATH {})".format(self.ctx["prefix"]),
                "set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)",
                "set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)",
                "set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)",
                "set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)",
            ])
            if cfg.get("cmake_emulator"):
                # run try_run() test binaries on the build host via the
                # declared emulator (wine for PE targets); WINEPATH points
                # at the sysroot bin/ so the test's DLL deps resolve
                emu = os.path.join(bdir, "cross-emulator.sh")
                winepath = "Z:" + self.ctx["prefix"].replace("/", "\\") \
                    + "\\bin"
                with open(emu, "w") as f:
                    f.write(
                        "# generated by ffmake from triplet '{}': "
                        "do not edit\n".format(self.ctx["triplet"]) +
                        "export WINEPATH='{}'\n".format(winepath) +
                        "exec {} \"$@\"\n".format(cfg["cmake_emulator"]))
                os.chmod(emu, 0o755)
                body += "\nset(CMAKE_CROSSCOMPILING_EMULATOR {})".format(emu)
            body += "\n"
        elif kind == "meson":
            path = os.path.join(bdir, "cross-file.ini")
            body = "\n".join([
                header,
                "[binaries]",
                "c = '{}gcc{}'".format(xp, cc_sfx),
                "cpp = '{}g++{}'".format(xp, cc_sfx),
                "ar = '{}ar'".format(xp),
                "strip = '{}strip'".format(xp),
                "windres = '{}windres'".format(xp),
                "pkg-config = 'pkg-config'",
                "",
                "[host_machine]",
                "system = '{}'".format(cfg["meson_system"]),
                "cpu_family = '{}'".format(cfg["meson_cpu_family"]),
                "cpu = '{}'".format(cfg["meson_cpu_family"]),
                "endian = 'little'",
            ]) + "\n"
        else:
            raise BuildError("unknown cross file kind: " + kind)
        with open(path, "w") as f:
            f.write(body)
        return path

    def _stamp_path(self, key, dep):
        return paths.stamp_file(self.ctx["root"], self.ns(dep), key)

    @staticmethod
    def _strip_reason(x):
        """`reason` documents WHY a recipe says what it says; it never
        changes what gets built. Keep it out of the ABI hash so writing
        rationale never invalidates stamps."""
        if isinstance(x, dict):
            return {k: Runner._strip_reason(v) for k, v in x.items()
                    if k != "reason"}
        if isinstance(x, list):
            return [Runner._strip_reason(v) for v in x]
        return x

    def _stamp_data(self, key, dep):
        """vcpkg-style ABI hash: the WHOLE recipe entry is the recipe.
        Hash the full dict (plus RECIPE_VERSION for engine-level bumps) so
        any edit invalidates the port automatically -- except `reason`."""
        source = dep.get("source") or {}
        payload = json.dumps({
            "recipe_version": RECIPE_VERSION,
            "entry": self._strip_reason(dep),
        }, sort_keys=True)
        return {
            "hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "rev": source.get("rev") or "",
            "url": source.get("url") or "",
            "args": dep.get("configure_args", []),
        }

    def read_stamp(self, key, dep):
        try:
            with open(self._stamp_path(key, dep)) as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def up_to_date(self, key, dep):
        old = self.read_stamp(key, dep)
        return bool(old) and old.get("hash") == self._stamp_data(key,
                                                                 dep)["hash"]

    def write_stamp(self, key, dep):
        with open(self._stamp_path(key, dep), "w") as f:
            json.dump(self._stamp_data(key, dep), f, indent=2, sort_keys=True)
            f.write("\n")

    @staticmethod
    def _sha256(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def _run_net(self, cmd, cwd, log_path):
        try:
            self.run(cmd, cwd, log_path, env=self.env(strict=False))
        except BuildError:
            proxy = os.environ.get("FFMAKE_PROXY") or FALLBACK_PROXY
            if not _proxy_reachable(proxy):
                print("network step failed; no proxy reachable at {} "
                      "(direct-only environment) -- not retrying".format(
                          proxy))
                raise
            print("network step failed; retrying via proxy {}".format(proxy))
            env = self.env(strict=False, extra={
                "https_proxy": proxy, "http_proxy": proxy})
            self.run(cmd, cwd, log_path, env=env)

    # git circuit breaker: without a low-speed timeout a stalled transfer
    # (googlesource/skia direct-connect lesson) hangs forever and never
    # trips _run_net's proxy fallback, which only fires on failure.
    GIT_SLOW = ["-c", "http.lowSpeedLimit=1000", "-c",
                "http.lowSpeedTime=30"]

    def distfile_path(self, source):
        """Content-addressed cache path: the sha256 pin is the key, so a
        present file is verified by construction. Unpinned sources fall
        back to the URL basename (and warn at verify time)."""
        d = paths.distfiles(self.ctx["root"])
        if source.get("sha256"):
            return os.path.join(
                d, source["sha256"] + os.path.splitext(source["url"])[1])
        return os.path.join(d, os.path.basename(source["url"]))

    def _mirror_path(self, key):
        return os.path.join(paths.git_mirrors(self.ctx["root"]),
                            key + ".git")

    def fetch_to(self, dst, source, key):
        """Clone/download `source` into dst. No stamp logic here; callers
        that need stamps wrap this via prepare(). dst must not exist."""
        stype = source.get("type")
        if stype == "git":
            mirror = self._mirror_path(key)
            if os.path.exists(mirror):
    # offline bootstrap; origin keeps pointing upstream so later
                # fetches reach the real source
                self.run(["git", "clone", "-q", mirror, dst],
                         self.ctx["root"],
                         os.path.join(self.ctx["logs"],
                                      key + "_clone.log"),
                         env=self.env(strict=False))
                self.run(["git", "-C", dst, "remote", "set-url",
                          "origin", source["url"]],
                         self.ctx["root"],
                         os.path.join(self.ctx["logs"],
                                      key + "_clone.log"),
                         env=self.env(strict=False))
            else:
                self._run_net(["git"] + self.GIT_SLOW
                              + ["clone", source["url"], dst],
                              self.ctx["root"],
                              os.path.join(self.ctx["logs"],
                                           key + "_clone.log"))
                # grow the farm from fresh objects (local hardlink clone)
                subprocess.run(["git", "clone", "--mirror", "-q", dst,
                                mirror])
            rev = source.get("rev")
            if rev:
                self.run(["git", "-C", dst, "checkout", "-q", rev],
                         self.ctx["root"],
                         os.path.join(self.ctx["logs"], key + "_checkout.log"),
                         env=self.env(strict=False))
            if source.get("submodules"):
    # shallow: submodules are build inputs, not history
                self.run(["git", "-C", dst] + self.GIT_SLOW
                         + ["submodule", "update",
                            "--init", "--depth", "1", "--recursive"],
                         self.ctx["root"],
                         os.path.join(self.ctx["logs"],
                                      key + "_submodules.log"),
                         env=self.env(strict=False))
        elif stype == "tar":
            url = source["url"]
            dist = self.distfile_path(source)
            pinned = source.get("sha256")
            if not os.path.exists(dist):
                tmp = dist + ".part"
                self._run_net(["curl", "-fL", "--retry", "3",
                               "-o", tmp, url],
                              self.ctx["root"],
                              os.path.join(self.ctx["logs"],
                                           key + "_download.log"))
                digest = self._sha256(tmp)
                if pinned and digest != pinned:
                    os.remove(tmp)
                    raise BuildError(
                        "{}: distfile sha256 mismatch\n"
                        "  expected: {}\n  actual:   {}\n"
                        "  if the upstream re-uploaded, re-pin the "
                        "hash".format(key, pinned, digest))
                os.replace(tmp, dist)
            # verify on every use: the key claims a digest, the bytes
            # must still match it (cache corruption detection)
            digest = self._sha256(dist)
            if pinned:
                if digest != pinned:
                    raise BuildError(
                        "{}: distfile sha256 mismatch\n"
                        "  expected: {}\n  actual:   {}\n"
                        "  delete the cached file and retry; if the "
                        "upstream re-uploaded, re-pin the hash".format(
                            key, pinned, digest))
            else:
                print("WARNING: {} has no sha256 pin "
                      "(actual: {})".format(key, digest))
            if dist.endswith(".zip"):
                import zipfile
                if not zipfile.is_zipfile(dist):
                    raise BuildError("unsupported archive: " + dist)
                tmp = dst + ".extract"
                if os.path.isdir(tmp):
                    shutil.rmtree(tmp)
                os.makedirs(tmp)
                with zipfile.ZipFile(dist) as z:
                    z.extractall(tmp)
            elif not tarfile.is_tarfile(dist):
                raise BuildError("unsupported archive: " + dist)
            else:
                tmp = dst + ".extract"
                if os.path.isdir(tmp):
                    shutil.rmtree(tmp)
                os.makedirs(tmp)
                with tarfile.open(dist) as t:
                    t.extractall(tmp)
            entries = [e for e in os.listdir(tmp)
                       if e != "pax_global_header" and not e.startswith(".")]
            os.makedirs(dst, exist_ok=True)
            if len(entries) == 1 and os.path.isdir(os.path.join(tmp, entries[0])):
                os.rename(os.path.join(tmp, entries[0]), dst)
            else:
                # multi-root archive (prebuilt packages): merge into dst
                for e in entries:
                    os.rename(os.path.join(tmp, e), os.path.join(dst, e))
            os.rmdir(tmp)
        else:
            raise BuildError("unknown source type: {}".format(stype))

    def prepare(self, key, dep):
        """Resolve (src, build_dir, logs_dir) for a port, fetching/wiping
        as the stamp dictates. src/ stays pristine across recipe changes.
        Returns (src, bdir, logs_dir) ready for an out-of-tree build."""
        root = self.ctx["root"]
        if self._in_source_builder(dep):
            # reached only on a stamp miss (up_to_date short-circuits in
            # build()); a re-earned build must start from pristine sources
            self._sanitize_src(os.path.join(paths.src(root), key),
                               dep.get("source"))
        ns = self.ns(dep)
        src = os.path.join(paths.src(root), key)
        bdir = paths.port_build_dir(root, ns, key)
        logs = paths.port_logs_dir(root, ns, key)
        old = self.read_stamp(key, dep)
        new = self._stamp_data(key, dep)
        source = dep.get("source") or {}
        if old and old.get("hash") == new["hash"] and \
                os.path.isdir(src) and os.path.isdir(bdir):
            return src, bdir, logs
        same_source = bool(old) and \
            old.get("rev") == new["rev"] and old.get("url") == new["url"]
        if not same_source:
            if not old and self._seeded_src(src, source):
                # offline-seeded tree: keep it and re-earn the stamp by
                # building; a real rev bump still re-fetches below
                print("dep {}: seeded src accepted (offline), stamp "
                      "re-earned on build".format(key))
                os.makedirs(logs, exist_ok=True)
                return src, bdir, logs
            # source changed (or first build): wipe both, re-fetch
            if os.path.isdir(src):
                shutil.rmtree(src)
            if os.path.isdir(bdir):
                shutil.rmtree(bdir)
            self.fetch_to(src, source, key)
        else:
            # only args/recipe changed: keep pristine src, rebuild
            if os.path.isdir(bdir):
                shutil.rmtree(bdir)
            if not os.path.isdir(src):
                self.fetch_to(src, source, key)
        os.makedirs(logs, exist_ok=True)
        return src, bdir, logs


    @staticmethod
    def _in_source_builder(dep):
        """Builders that compile inside the vendor tree (custom `cd {src}`
        steps, prefixup sed -i) mutate src/, and that state leaks across
        triplets sharing the tree -- a mingw object farm will poison the
        next linux build with __imp__-prefixed symbols. Such ports get a
        forced sanitize on every stamp-miss rebuild."""
        if dep.get("system") == "custom":
    # a custom recipe is an operation sequence over the vendor tree
            # in any shape (cd, make -C, plain cp) -- pristine start
            return True
        prefixup = dep.get("prefixup") or ""
        return "sed -i" in prefixup and "{src}" in prefixup

    def _sanitize_src(self, src, source):
        import subprocess as _sp
        if (source or {}).get("type") == "git" and \
                os.path.exists(os.path.join(src, ".git")):
            _sp.run(["git", "-C", src, "clean", "-xfd"], capture_output=True)
            _sp.run(["git", "-C", src, "checkout", "-q", "-f", "HEAD"],
                    capture_output=True)
            return
        import shutil as _sh
        _sh.rmtree(src, ignore_errors=True)
        self.fetch_to(src, source or {}, "sanitize")

    @staticmethod
    def _seeded_src(src, source):
        """Offline-seeded vendor tree acceptance (cold start only)."""
        if not os.path.isdir(src):
            return False
        stype = (source or {}).get("type")
        if stype == "git":
            return os.path.exists(os.path.join(src, ".git"))
        if stype == "tar":
            return bool(os.listdir(src))
        return False

    def cross_args(self, dep=None):
        """Autotools cross args for the current triplet (empty for native).

        --host is standard autoconf and universal. --cross-prefix is an
        ffmpeg/x264 configure-ism, so it is opt-in via dep["cross_prefix"].
        Ports managing their own cross plumbing (openssl's Configure)
        declare "no_cross_args": true.
        """
        cp = self.ctx["triplet_cfg"]["cross_prefix"]
        if not cp:
            return []
        # host tools always build natively, whatever the triplet says
        if dep is not None and dep.get("tool"):
            return []
        if dep is not None and dep.get("no_cross_args"):
            return []
        args = ["--host=" + cp.rstrip("-")]
        if dep is not None and dep.get("cross_prefix"):
            args.append("--cross-prefix=" + cp)
        return args
