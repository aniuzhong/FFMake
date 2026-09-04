"""Host cross-toolchain provisioning (toolchains.json).

Cross toolchains (llvm-mingw, ...) are triplet-independent host tools: they
live in the shared tools sysroot, outside any triplet's port closure. The
repo-root manifest pins url + sha256 so every environment (Kylin host,
container, GH runner) provisions byte-identical toolchains on demand;
triplets declare the dependency via triplet_cfg "cross_toolchain":
"<name>/bin".

Provisioning is idempotent and self-verifying: a toolchain is present iff
its "check" binary exists; otherwise the pinned tarball is downloaded into
distfiles (cache shared with ports), sha256-verified and unpacked.
"""

import json
import os
import shutil
import subprocess
import tarfile
import tempfile

from . import paths
from .runners.base import FALLBACK_PROXY, BuildError


def manifest_path(root):
    return os.path.join(root, "toolchains.json")


def _load(root):
    path = manifest_path(root)
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _curl(url, dst, workdir):
    """Download with the engine's network policy: direct first, one retry
    through the fallback proxy (same as runners' _run_net). Output lands in
    a log file whose tail is printed on failure."""
    os.makedirs(workdir, exist_ok=True)
    log = os.path.join(workdir, "toolchain_download.log")
    cmd = ["curl", "-fL", "--retry", "3", "-o", dst, url]

    def _attempt(env_extra=None):
        env = dict(os.environ)
        if env_extra:
            env.update(env_extra)
        with open(log, "w") as f:
            return subprocess.run(cmd, stdout=f,
                                  stderr=subprocess.STDOUT,
                                  env=env).returncode

    rc = _attempt()
    if rc != 0:
        proxy = os.environ.get("FFMAKE_PROXY") or FALLBACK_PROXY
        print("toolchain download failed; retrying via proxy {}".format(
            proxy))
        rc = _attempt({"https_proxy": proxy, "http_proxy": proxy})
    if rc != 0:
        from .runners.base import _log_tail
        print("toolchain download failed (exit {})\n{}".format(
            rc, _log_tail(log)))
        raise BuildError("toolchain download failed: {}".format(url))


def ensure(root, triplet_cfg):
    """Provision every toolchain the triplet declares. Safe to call on every
    verb: present toolchains are a no-op."""
    tc = triplet_cfg.get("cross_toolchain")
    if not tc:
        return
    name = tc.split("/")[0]
    entries = _load(root)
    entry = entries.get(name)
    if entry is None:
        raise BuildError(
            "triplet declares cross_toolchain '{}' but {} has no entry "
            "for it -- add one (url + sha256 + check)".format(
                tc, manifest_path(root)))

    dest = os.path.join(paths.tools_prefix(root), name)
    check = os.path.join(dest, entry["check"])
    if os.path.exists(check):
        return

    if not entry.get("sha256"):
        raise BuildError(
            "toolchain '{}' has no sha256 pin in {} -- refusing to "
            "fetch unpinned binaries".format(name, manifest_path(root)))

    os.makedirs(paths.distfiles(root), exist_ok=True)
    dist = os.path.join(paths.distfiles(root), os.path.basename(entry["url"]))
    if not os.path.exists(dist):
        print("toolchain {}: fetching {}".format(name, entry["url"]))
        _curl(entry["url"], dist,
              os.path.join(paths.build(root), "tools"))
    digest = _sha256(dist)
    if digest != entry["sha256"]:
        raise BuildError(
            "toolchain '{}' sha256 mismatch\n"
            "  expected: {}\n  actual:   {}\n"
            "  delete the cached file and retry; if the upstream "
            "re-uploaded, re-pin the hash".format(name, entry["sha256"],
                                                  digest))

    print("toolchain {}: provisioning -> {}".format(name, dest))
    os.makedirs(dest, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(dist) as tf:
            tf.extractall(tmp)  # pinned archive; contents audited by hash
        roots = [os.path.join(tmp, n) for n in os.listdir(tmp)]
        if len(roots) != 1 or not os.path.isdir(roots[0]):
            raise BuildError(
                "toolchain '{}': archive root layout unexpected".format(name))
        for item in os.listdir(roots[0]):
            src = os.path.join(roots[0], item)
            dst = os.path.join(dest, item)
            if os.path.isdir(src) and not os.path.islink(src):
                shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
    if not os.path.exists(check):
        raise BuildError(
            "toolchain '{}': check binary missing after unpack: {}".format(
                name, check))
    print("toolchain {}: ready ({})".format(name, entry["check"]))


def report(root):
    """Probe helper: status of every declared toolchain (non-fatal)."""
    for name, entry in sorted(_load(root).items()):
        check = os.path.join(paths.tools_prefix(root), name,
                             entry.get("check", ""))
        print("toolchain {:<12} {}".format(
            name, "present" if os.path.exists(check) else "MISSING "
            "(provisioned on demand by build verbs)"))
