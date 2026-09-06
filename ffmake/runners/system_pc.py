"""system-pc runner: declare a host library inside the sysroot.

Some ports depend on libraries we deliberately do not build (the
system-satisfaction tier). In strict pkg-config mode their .pc files
must exist in the sysroot or the Requires chains of our own .pc files
break. This runner copies the host .pc files into the triplet sysroot,
following the recursive Requires/Requires.private closure -- a deep
chain (librsvg -> gio -> gobject -> glib -> libpcre/libffi/mount...)
is collected automatically instead of being maintained by hand.

The .pc contents keep pointing at host paths: the library binaries
still come from the OS (the linker finds them in the default system
search path), only the metadata is mirrored.
"""

import glob
import os
import re

from .base import BuildError, Runner

# host pkg-config search dirs (Debian-likes: multiarch + share)
_SYSTEM_PC_DIRS = [
    "/usr/lib/x86_64-linux-gnu/pkgconfig",
    "/usr/share/pkgconfig",
    "/usr/local/lib/x86_64-linux-gnu/pkgconfig",
    "/usr/local/share/pkgconfig",
]

_REQUIRES = re.compile(r"^(Requires(?:\.private)?[ \t]*:[ \t]*)(.*)$", re.M)


def _find_host_pc(name):
    for d in _SYSTEM_PC_DIRS:
        hits = glob.glob(os.path.join(d, name + ".pc"))
        if hits:
            return hits[0]
    return None


def _requires_of(pc_text):
    """Split Requires/Requires.private references into (mandatory,
    optional): plain Requires entries are hard (a missing one breaks the
    chain), Requires.private entries are best-effort (pkg-config itself
    only needs them for static linking). Empty values yield nothing --
    some host .pc files have bare "Requires.private:" lines."""
    must, optional = set(), set()
    for m in _REQUIRES.finditer(pc_text):
        bucket = optional if m.group(0).startswith("Requires.private") \
                 else must
        skip_version = False
        for tok in re.split(r"[\s,]+", m.group(2).strip()):
            tok = tok.strip(" ,")
            if not tok:
                continue
            if skip_version:
                skip_version = False
                continue
            if re.fullmatch(r"[<>=]+", tok):
                # operator: its version literal is not a name
                skip_version = True
                continue
            bucket.add(tok)
    return must, optional


def _collect_closure(seeds, copied):
    """Recursively resolve Requires over the host dirs; returns the list
    of host .pc files to copy (BFS, cycles guarded by `copied`). Plain
    Requires entries must resolve; Requires.private entries are copied
    when present and skipped otherwise."""
    todo = [(name, True) for name in seeds]
    files = []
    while todo:
        name, mandatory = todo.pop(0)
        if not name or name in copied:
            continue
        host = _find_host_pc(name)
        if host is None:
            if mandatory:
                raise BuildError(
                    "system-pc: '{}' not found in {} -- is the host -dev "
                    "package installed?".format(name, _SYSTEM_PC_DIRS[:2]))
            continue
        copied.add(name)
        files.append((name, host))
        must, optional = _requires_of(
            open(host, errors="ignore").read())
        todo.extend((n, True) for n in sorted(must))
        todo.extend((n, False) for n in sorted(optional))
    return files


class SystemPcRunner(Runner):
    system = "system-pc"

    def build(self, key, dep):
        if self.up_to_date(key, dep):
            print("dep {}: up to date, skip".format(key))
            return
        pcdir = os.path.join(self.ctx["prefix"], "lib", "pkgconfig")
        os.makedirs(pcdir, exist_ok=True)
        seeds = dep.get("pcs", [dep.get("pc", key)])
        copied = set()
        files = _collect_closure(sorted(seeds), copied)
        for name, host in files:
            dst = os.path.join(pcdir, name + ".pc")
            with open(host, errors="ignore") as f:
                text = f.read()
            with open(dst, "w") as f:
                f.write(text)
        self.write_stamp(key, dep)
        print("dep {}: system pc closure declared -> {} ({} files: {})".format(
            key, pcdir, len(files),
            ", ".join(n for n, _ in files)))
