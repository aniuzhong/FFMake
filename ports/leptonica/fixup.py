"""leptonica_config fixup: repair the installed LeptonicaConfig.cmake.

Leptonica detects WebP/OpenJPEG via pkg-config, so the cmake config it
installs guards its find_dependency calls with empty conditions
("if ()"): the template variables it was configure_file'd from don't
exist in that detection path. Downstream consumers (tesseract) then
fail on leptonica's imported-target interface, which references
WebP::webp. Re-arm the guards from sysroot reality (.pc presence).
Idempotent.
"""

import glob
import os
import re
import sys


def _has_pc(prefix, stem):
    return bool(glob.glob(os.path.join(
        prefix, "lib", "pkgconfig", stem + "*.pc")))


def _resolve_bare_linkonly(prefix, path):
    """Leptonica found some image libs via pkg-config, so its exported
    targets carry bare "$<LINK_ONLY:openjp2>"-style names instead of
    target refs or paths. Downstream consumers (tesseract) then link
    with -lopenjp2 and no -L, failing. Rewrite each resolvable bare
    name to the sysroot library path. Idempotent by construction."""
    with open(path) as f:
        body = f.read()

    def repl(m):
        name = m.group(1)
        hits = glob.glob(os.path.join(prefix, "lib",
                                      "lib{}.so".format(name)))
        return "$<LINK_ONLY:{}>".format(hits[0]) if hits else m.group(0)

    new = re.sub(r"\$<LINK_ONLY:([^:$>]+)>", repl, body)
    if new != body:
        with open(path, "w") as f:
            f.write(new)
        print("fixup leptonica_config: resolved bare LINK_ONLY names "
              "in {}".format(path))


def run(ctx, key, dep):
    run_lept_pc(ctx, key, dep)
    _config_run(ctx, key, dep)


def _config_run(ctx, key, dep):
    prefix = ctx["prefix"]
    cmake_dir = os.path.join(prefix, "lib", "cmake", "leptonica")
    targets = os.path.join(cmake_dir, "LeptonicaTargets.cmake")
    if os.path.isfile(targets):
        _resolve_bare_linkonly(prefix, targets)
    path = os.path.join(cmake_dir, "LeptonicaConfig.cmake")
    if not os.path.isfile(path):
        return
    with open(path) as f:
        body = f.read()
    if "if ()" not in body:
        return
    conds = {
        "find_dependency(OpenJPEG CONFIG)":
            _has_pc(prefix, "openjpeg"),
        "find_dependency(WebP 0.5.0 CONFIG)":
            _has_pc(prefix, "libwebp"),
    }
    for dep_call, ok in conds.items():
        old = "if ()\n    {}\nendif()".format(dep_call)
        new = "if ({})\n    {}\nendif()".format(
            "TRUE" if ok else "FALSE", dep_call)
        if old in body:
            body = body.replace(old, new)
    with open(path, "w") as f:
        f.write(body)
    print("fixup leptonica_config: re-armed find_dependency guards "
          "in {}".format(path))


# --- phase 1: ensure leptonica.pc exists (recovered lept_pc) ---
def run_lept_pc(ctx, key, dep):
    pcdir = os.path.join(ctx["prefix"], "lib", "pkgconfig")
    src = os.path.join(pcdir, "lept_Release.pc")
    dst = os.path.join(pcdir, "lept.pc")
    if os.path.exists(src) and not os.path.exists(dst):
        os.replace(src, dst)
        print("fixup lept_pc: {} -> {}".format(src, dst))
