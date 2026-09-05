"""Knowledge loader: ports/ + profiles/ + policy are the only inputs.

The TOML trees are the model; this module is their single typed door.
Recipe dicts produced here are field-for-field identical to the
predecessor deps.json entries (golden-tested), which is what keeps the
ABI-hash stamps continuous.
"""

import glob
import os
import shlex

import tomli


def load_universe(root):
    uni = {}
    for p in sorted(glob.glob(os.path.join(root, "ports", "*", "port.toml"))):
        key = os.path.basename(os.path.dirname(p))
        with open(p, "rb") as f:
            uni[key] = tomli.load(f)
    return uni


def triplets(root):
    return sorted(os.path.basename(p)[:-5] for p in
                  glob.glob(os.path.join(root, "profiles", "*.toml")))


def load_profile(root, triplet):
    with open(os.path.join(root, "profiles", triplet + ".toml"), "rb") as f:
        return tomli.load(f)


def load_flags(root, triplet):
    """Pass-through FFmpeg configure flags. The per-triplet features file
    REPLACES the global one (cross-platform trimming semantics)."""
    per = os.path.join(root, "policy", "features.%s.txt" % triplet)
    path = per if os.path.isfile(per) else os.path.join(
        root, "policy", "features.txt")
    flags = []
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#"):
            flags.extend(shlex.split(line))
    return flags
