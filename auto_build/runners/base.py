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

from .. import env as env_mod
from .. import paths
from .. import triplets as triplets_mod

# Bump to invalidate all stamps after recipe changes.
RECIPE_VERSION = 2

# User-provided local proxy; used as fallback when a network step fails.
FALLBACK_PROXY = "http://127.0.0.1:10808"


class BuildError(Exception):
    pass


class Runner(object):
    system = "base"

    def __init__(self, ctx):
        self.ctx = ctx

    # --- namespace routing -------------------------------------------------
    def ns(self, dep):
        """Stamps/build trees are namespaced: host tools vs per-triplet."""
        return paths.TOOLS_NS if dep.get("tool") else self.ctx["triplet"]

    def install_prefix(self, dep):
        """Host tools install to the shared tools sysroot; everything
        else installs into the per-triplet sysroot."""
        return self.ctx["tools_prefix"] if dep.get("tool") \
            else self.ctx["prefix"]

    # --- plumbing ---------------------------------------------------------
    def env(self, strict=True, extra=None):
        return env_mod.build_child_env(
            self.ctx["prefix"], strict_pkgconfig=strict,
            tools_bin=os.path.join(self.ctx["tools_prefix"], "bin"),
            extra=extra)

    def run(self, cmd, cwd, log_path, env=None):
        with open(log_path, "w") as f:
            rc = subprocess.run(cmd, cwd=cwd, env=env or self.env(),
                                stdout=f, stderr=subprocess.STDOUT).returncode
        if rc != 0:
            raise BuildError("{} failed in {} (see {})".format(
                cmd[0], cwd, log_path))

    # --- stamps (JSON: hash + rev/url + args) ------------------------------
    def _stamp_path(self, key, dep):
        return paths.stamp_file(self.ctx["root"], self.ns(dep), key)

    def _stamp_data(self, key, dep):
        source = dep.get("source") or {}
        payload = json.dumps({
            "recipe": self.system,
            "recipe_version": RECIPE_VERSION,
            "rev": source.get("rev") or "",
            "args": dep.get("configure_args", []),
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

    # --- fetching ---------------------------------------------------------
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
            env = self.env(strict=False, extra={
                "https_proxy": proxy, "http_proxy": proxy})
            print("network step failed; retrying via proxy {}".format(proxy))
            self.run(cmd, cwd, log_path, env=env)

    def fetch_to(self, dst, source, key):
        """Clone/download `source` into dst. No stamp logic here; callers
        that need stamps wrap this via prepare(). dst must not exist."""
        stype = source.get("type")
        if stype == "git":
            self._run_net(["git", "clone", source["url"], dst],
                          self.ctx["root"],
                          os.path.join(self.ctx["logs"], key + "_clone.log"))
            rev = source.get("rev")
            if rev:
                # plain clone + checkout: works for branches, tags and
                # pinned commit hashes alike
                self.run(["git", "-C", dst, "checkout", "-q", rev],
                         self.ctx["root"],
                         os.path.join(self.ctx["logs"], key + "_checkout.log"),
                         env=self.env(strict=False))
        elif stype == "tar":
            url = source["url"]
            dist = os.path.join(paths.distfiles(self.ctx["root"]),
                                os.path.basename(url))
            if not os.path.exists(dist):
                self._run_net(["curl", "-fL", "--retry", "3",
                               "-o", dist, url],
                              self.ctx["root"],
                              os.path.join(self.ctx["logs"],
                                           key + "_download.log"))
            # verify on every use (cache corruption detection), vcpkg-style
            pinned = source.get("sha256")
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
            if not tarfile.is_tarfile(dist):
                raise BuildError("unsupported archive: " + dist)
            tmp = dst + ".extract"
            if os.path.isdir(tmp):
                shutil.rmtree(tmp)
            os.makedirs(tmp)
            with tarfile.open(dist) as t:
                t.extractall(tmp)
            entries = [e for e in os.listdir(tmp)
                       if e != "pax_global_header" and not e.startswith(".")]
            if len(entries) != 1:
                raise BuildError("tarball {}: expected one top-level dir, "
                                 "got {}".format(dist, entries))
            os.rename(os.path.join(tmp, entries[0]), dst)
            os.rmdir(tmp)
        else:
            raise BuildError("unknown source type: {}".format(stype))

    def prepare(self, key, dep):
        """Resolve (src, build_dir, logs_dir) for a port, fetching/wiping
        as the stamp dictates. src/ stays pristine across recipe changes.
        Returns (src, bdir, logs_dir) ready for an out-of-tree build."""
        root = self.ctx["root"]
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

    # --- cross-compilation helpers ----------------------------------------
    def cross_args(self):
        """Autotools cross args for the current triplet (empty for native)."""
        cp = self.ctx["triplet_cfg"]["cross_prefix"]
        if not cp:
            return []
        return ["--host=" + cp.rstrip("-"), "--cross-prefix=" + cp]
