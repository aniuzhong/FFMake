"""Repository and workspace path conventions (single source of truth).

Layout is per-triplet (vcpkg style): everything under out/<triplet>/ is one
sysroot; host tools live in workspace/tools/ shared by all triplets;
build trees and stamps are namespaced by triplet (or "tools" for host
tools). Only workspace/.gitkeep is tracked; structure is rebuilt here.
"""

import os

# Host tools (nasm, ...) shared by every triplet.
TOOLS_NS = "tools"


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
