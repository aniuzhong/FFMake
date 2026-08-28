"""L1 runner base: fetching, stamps, logging, child env."""

import hashlib
import json
import os
import shutil
import subprocess
import tarfile

from .. import env as env_mod
from .. import paths

# Bump to invalidate all stamps after recipe changes.
RECIPE_VERSION = 1

# User-provided local proxy; used as fallback when a network step fails.
FALLBACK_PROXY = "http://127.0.0.1:10808"


class BuildError(Exception):
    pass


class Runner(object):
    system = "base"

    def __init__(self, ctx):
        self.ctx = ctx

    # --- plumbing ---------------------------------------------------------
    def env(self, strict=True, extra=None):
        return env_mod.build_child_env(
            self.ctx["prefix"], strict_pkgconfig=strict, extra=extra)

    def run(self, cmd, cwd, log_name, env=None):
        log = os.path.join(self.ctx["logs"], log_name)
        with open(log, "w") as f:
            rc = subprocess.run(cmd, cwd=cwd, env=env or self.env(),
                                stdout=f, stderr=subprocess.STDOUT).returncode
        if rc != 0:
            raise BuildError("{} failed in {} (see {})".format(
                cmd[0], cwd, log))

    # --- stamps (content hash: recipe + source rev + configure args) ------
    def _stamp_path(self, key):
        return os.path.join(paths.stamps(self.ctx["root"]), key + ".txt")

    def _stamp_key(self, key, dep):
        source = dep.get("source") or {}
        payload = json.dumps({
            "recipe": self.system,
            "recipe_version": RECIPE_VERSION,
            "rev": source.get("rev") or source.get("url"),
            "args": dep.get("configure_args", []),
        }, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def up_to_date(self, key, dep):
        path = self._stamp_path(key)
        if not os.path.exists(path):
            return False
        with open(path) as f:
            return f.read().strip() == self._stamp_key(key, dep)

    def write_stamp(self, key, dep):
        with open(self._stamp_path(key), "w") as f:
            f.write(self._stamp_key(key, dep) + "\n")

    # --- fetching ---------------------------------------------------------
    def _run_net(self, cmd, cwd, log_name):
        try:
            self.run(cmd, cwd, log_name, env=self.env(strict=False))
        except BuildError:
            proxy = os.environ.get("FFMAKE_PROXY") or FALLBACK_PROXY
            env = self.env(strict=False, extra={
                "https_proxy": proxy, "http_proxy": proxy})
            print("network step failed; retrying via proxy {}".format(proxy))
            self.run(cmd, cwd, log_name, env=env)

    def fetch_to(self, dst, source, key):
        """Clone/download `source` into dst. No stamp logic here; callers
        that need stamps wrap this via fetch(). dst must not exist."""
        stype = source.get("type")
        if stype == "git":
            self._run_net(["git", "clone", source["url"], dst],
                          self.ctx["root"], key + "_clone.log")
            rev = source.get("rev")
            if rev:
                # plain clone + checkout: works for branches, tags and
                # pinned commit hashes alike
                self.run(["git", "-C", dst, "checkout", "-q", rev],
                         self.ctx["root"], key + "_checkout.log",
                         env=self.env(strict=False))
        elif stype == "tar":
            url = source["url"]
            dist = os.path.join(paths.distfiles(self.ctx["root"]),
                                os.path.basename(url))
            if not os.path.exists(dist):
                self._run_net(["curl", "-fL", "--retry", "3",
                               "-o", dist, url],
                              self.ctx["root"], key + "_download.log")
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

    def fetch(self, key, dep):
        """Return the source dir, fetching if needed.

        Stamp mismatch -> wipe the source tree and re-fetch (cheap, keeps
        vendor trees clean instead of accumulating build residue).
        """
        src = os.path.join(paths.src(self.ctx["root"]), key)
        if self.up_to_date(key, dep) and os.path.isdir(src):
            return src
        if os.path.isdir(src):
            shutil.rmtree(src)
        self.fetch_to(src, dep.get("source") or {}, key)
        return src
