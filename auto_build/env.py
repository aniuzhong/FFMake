"""L0 environment layer: build child-process environment whitelist.

Semantics:
- Inherit only whitelisted user-level variables; build-sensitive variables
  (PYTHONPATH, LD_LIBRARY_PATH, CFLAGS, ...) are always scrubbed, so leaks
  from shell rc files, pip environments, or user exports are blocked.
- PATH is narrowed to <prefix>/bin:/usr/bin:/bin: toolchain binaries
  (nasm/meson/ninja) come from the prefix; /usr/local and user-defined
  paths are excluded.
- pkg-config dual mode:
    prefix-first (default)  prefix takes priority, system .pc files remain
                            the fallback -- used for the FFmpeg configure run.
    strict (PKG_CONFIG_LIBDIR pinned to prefix) system .pc files invisible --
                            used for dependency builds, so "deps of deps"
                            always resolve to the unified prefix, not system.

Limitation: link-time system library search (cmake find_library etc.) is out
of scope for this layer; it is covered by post-install invariant validation
and RPATH discipline.
"""

import os

# User-level variables whitelisted for inheritance by child processes.
# Proxy vars are included: git clone / curl fetches legitimately need them.
_INHERIT = (
    "HOME", "USER", "LOGNAME", "SHELL", "TERM",
    "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR",
    "http_proxy", "https_proxy", "no_proxy", "all_proxy",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY",
)

# Build-sensitive variables: scrubbed even if present in the parent env
_SCRUB = (
    "PYTHONPATH", "PYTHONHOME",
    "PKG_CONFIG_PATH", "PKG_CONFIG_LIBDIR",
    "CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH",
    "LIBRARY_PATH", "LD_LIBRARY_PATH", "LD_RUN_PATH",
    "ACLOCAL_PATH", "CMAKE_PREFIX_PATH",
    "CC", "CXX", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS",
)

_SYSTEM_PATH = "/usr/bin:/bin"


def build_child_env(prefix, strict_pkgconfig=False, pythonpath=None, extra=None):
    """Build the child-process environment.

    prefix            unified per-arch prefix (workspace/out/x86_64)
    strict_pkgconfig  True -> PKG_CONFIG_LIBDIR hides system .pc files
    pythonpath        controlled injection point for toolchains like meson
                      (None = not set)
    extra             runner-level extras (applied last, may override above)
    """
    child = {k: os.environ[k] for k in _INHERIT if k in os.environ}
    for k in _SCRUB:
        # Belt and braces: whitelist inheritance already excludes these;
        # this guards against future whitelist growth re-introducing them.
        child.pop(k, None)

    child["PATH"] = os.path.join(prefix, "bin") + ":" + _SYSTEM_PATH
    pcdir = os.path.join(prefix, "lib", "pkgconfig")
    child["PKG_CONFIG_PATH"] = pcdir
    if strict_pkgconfig:
        # LIBDIR wholesale replaces the default pkg-config search dirs,
        # which makes system .pc files invisible.
        child["PKG_CONFIG_LIBDIR"] = pcdir
    if pythonpath is not None:
        child["PYTHONPATH"] = pythonpath
    if extra:
        child.update(extra)
    return child
