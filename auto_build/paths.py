"""Repository and workspace path conventions (single source of truth).

Layout is per-triplet (vcpkg style): everything under out/<triplet>/ is one
sysroot; host tools live in workspace/tools/ shared by all triplets;
build trees and stamps are namespaced by triplet (or "tools" for host
tools). Only workspace/.gitkeep is tracked; structure is rebuilt here.
"""

import hashlib
import json
import os
import shutil

# Host tools (nasm, ...) shared by every triplet.
TOOLS_NS = "tools"

# pkg-config wrapper installed into tools/bin:
# 1) pkg-config 0.29 "escapes" non-ASCII bytes as backslash+byte (5C E4),
#    which is INVALID UTF-8 and crashes meson's strict decoding -> undo it
# 2) rewrites real sysroot prefixes to their ASCII aliases (see
#    ensure_ascii_alias) so all pkg-config text stays ASCII-clean
PKG_CONFIG_WRAPPER = """#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys

REAL = "/usr/bin/pkg-config"
pkgmap = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "pkgmap.json")
mapping = {}
try:
    with open(pkgmap) as f:
        mapping = json.load(f)
except (OSError, ValueError):
    pass
r = subprocess.run([REAL] + sys.argv[1:], capture_output=True)
out = re.sub(rb"\\\\([\\x80-\\xff])", rb"\\1", r.stdout)
for real, alias in mapping.items():
    out = out.replace(real.encode("utf-8"), alias.encode("ascii"))
sys.stdout.buffer.write(out)
sys.stderr.buffer.write(r.stderr)
sys.exit(r.returncode)
"""


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def workspace(root=None):
    return os.path.join(root or repo_root(), "workspace")


def distfiles(root=None):
    return os.path.join(workspace(root), "distfiles")


def src(root=None):
    return os.path.join(workspace(root), "src")


def build(root=None):
    return os.path.join(workspace(root), "build")


def logs(root=None):
    return os.path.join(workspace(root), "logs")


def tools_prefix(root=None):
    """Host tools sysroot (nasm etc.), shared across triplets."""
    return os.path.join(workspace(root), "tools")


def out(root, triplet):
    """Per-triplet sysroot root."""
    return os.path.join(workspace(root), "out", triplet)


def prefix(root, triplet):
    """Unified per-triplet prefix: install target of third-party deps and
    FFmpeg itself."""
    return out(root, triplet)


def port_build_dir(root, ns, key):
    """Per-port out-of-tree build dir (vcpkg's buildtrees/<port> analog).
    ns is a triplet name or TOOLS_NS. Keeps vendor src/ pristine."""
    return os.path.join(build(root), ns, key)


def port_logs_dir(root, ns, key):
    """Per-port build logs, colocated with the build tree."""
    return os.path.join(port_build_dir(root, ns, key), "logs")


def ffmpeg_out(root, triplet):
    """Per-triplet out-of-tree FFmpeg build dir."""
    return os.path.join(build(root), triplet, "ffmpeg-out")


def stamp_file(root, ns, key):
    return os.path.join(workspace(root), "var", "stamps", ns, key + ".json")


def lock_file(root=None):
    """Resolved-closure snapshot at the repo root (tracked in git)."""
    return os.path.join(root or repo_root(), "lock.json")


def ascii_alias_root(root=None):
    """ASCII-only mirror of the workspace under /tmp.

    pkg-config prints sysroot paths as text; when the repo lives under a
    non-ASCII path (~/仓库) consumers like meson crash decoding them. All
    pkg-config traffic goes through ASCII alias symlinks instead.
    """
    import hashlib
    tag = hashlib.md5(workspace(root).encode("utf-8")).hexdigest()[:8]
    return os.path.join("/tmp", "ffmake-" + tag)


def sysroot_alias(root, triplet):
    """ASCII alias of out/<triplet> (created by ensure_ascii_alias)."""
    return os.path.join(ascii_alias_root(root), "sysroot-" + triplet)


def pkgmap_file(root=None):
    """real-prefix -> ascii-alias mapping consumed by the pkg-config wrapper."""
    return os.path.join(workspace(root), "tools", "pkgmap.json")


def ensure_ascii_alias(root=None, triplet=None):
    """Create/refresh ASCII alias symlinks and the pkg-config wrapper."""
    root = root or repo_root()
    base = ascii_alias_root(root)
    os.makedirs(base, exist_ok=True)
    mapping = {}
    links = {"sysroot-" + TOOLS_NS: tools_prefix(root)}
    if triplet:
        links["sysroot-" + triplet] = out(root, triplet)
        links["build-" + triplet] = build(root)
    for name, target in links.items():
        alias = os.path.join(base, name)
        if os.path.islink(alias):
            os.remove(alias)
        elif os.path.isdir(alias):
            shutil.rmtree(alias)
        os.symlink(target, alias)
        mapping[target] = alias
    with open(pkgmap_file(root), "w") as f:
        json.dump(mapping, f, indent=2, sort_keys=True)
    wrapper = os.path.join(tools_prefix(root), "bin", "pkg-config")
    with open(wrapper, "w") as f:
        f.write(PKG_CONFIG_WRAPPER)
    os.chmod(wrapper, 0o755)
    return base


def ffmpeg_src_dir(root=None):
    """Default in-workspace FFmpeg source tree (auto-cloned if absent)."""
    return os.path.join(src(root), "ffmpeg")


def ensure_workspace(root=None, triplet=None):
    root = root or repo_root()
    dirs = [
        "distfiles",
        "src",
        os.path.join("tools", "bin"),
        "logs",
        os.path.join("var", "stamps", TOOLS_NS),
    ]
    if triplet:
        dirs += [
            os.path.join("build", triplet, "ffmpeg-out"),
            os.path.join("out", triplet, "lib", "pkgconfig"),
            os.path.join("out", triplet, "include"),
            os.path.join("out", triplet, "bin"),
            os.path.join("var", "stamps", triplet),
        ]
    for d in dirs:
        os.makedirs(os.path.join(workspace(root), d), exist_ok=True)
    return workspace(root)
