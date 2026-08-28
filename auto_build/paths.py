"""Repository and workspace path conventions (single source of truth)."""

import os

OUT_ARCH = "x86_64"

# Relative dirs created by ensure_workspace() inside the workspace.
# lib/pkgconfig is pre-created so the PKG_CONFIG_LIBDIR target exists from
# the start; var/stamps holds content-hash stamps; build/ffmpeg-out is the
# out-of-tree FFmpeg build dir.
_DIRS = (
    "distfiles",
    "src",
    "build/ffmpeg-out",
    "out/{}/3rd/lib/pkgconfig".format(OUT_ARCH),
    "out/{}/3rd/include".format(OUT_ARCH),
    "out/{}/3rd/bin".format(OUT_ARCH),
    "logs",
    "var/stamps",
)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def workspace(root=None):
    return os.path.join(root or repo_root(), "workspace")


def prefix(root=None):
    """Unified prefix: install target of all third-party libs and FFmpeg."""
    return os.path.join(workspace(root), "out", OUT_ARCH, "3rd")


def src(root=None):
    return os.path.join(workspace(root), "src")


def ffmpeg_src_dir(root=None):
    """Default in-workspace FFmpeg source tree (auto-cloned if absent)."""
    return os.path.join(src(root), "ffmpeg")


def distfiles(root=None):
    return os.path.join(workspace(root), "distfiles")


def logs(root=None):
    return os.path.join(workspace(root), "logs")


def stamps(root=None):
    return os.path.join(workspace(root), "var", "stamps")


def ffmpeg_out(root=None):
    """Out-of-tree FFmpeg build dir (keeps the upstream tree pristine)."""
    return os.path.join(workspace(root), "build", "ffmpeg-out")


def ensure_workspace(root=None):
    root = root or repo_root()
    for d in _DIRS:
        os.makedirs(os.path.join(workspace(root), d), exist_ok=True)
    return workspace(root)
