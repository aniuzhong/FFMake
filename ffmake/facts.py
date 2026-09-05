"""store/facts: execution-verified knowledge.

Three facts, all derived from the configured ffmpeg rev and the installed
sysroot (never from prose):
  constraints.<rev>.json   version intervals ffmpeg's configure demands,
                           harvested from the same quoted pkg-config specs
                           the demand extractor reads
  installed.json           pkg-config version of every installed port,
                           backfilled at validate time
Preflight (for upgrade/canary reports) compares the two: a configured
interval the installed version violates is exactly the "built it, too
old, loop spins" failure mode, reported before a single compile.
"""

import json
import os
import re
import subprocess

# quoted pkg-config specs carrying version ops: "aom >= 2.0.0",
# "ffnvcodec >= 11.1.5.3 ffnvcodec < 12.0"
_SPEC = re.compile(r'"([^"]+)"')
_TERM = re.compile(r'([\w.+\-]+)\s*(>=|<=|==|=|<|>)\s*([\w.]+)')


# a quoted spec is a constraint source only if it reads like one: first
# word is the library name, every versioned term names that same library,
# and it is not an error message ("ERROR: OpenSSL <3.0.0 is incompatible"
# would otherwise supply a phantom upper bound)
_MSG = re.compile(r"ERROR|requires|incompatible|not found", re.I)


def extract_constraints(cfg_path):
    """name -> [group, ...]; each group is {op: version} and the groups
    are alternatives -- ffmpeg checks the same library against several
    intervals (ffnvcodec's three windows)."""
    out = {}
    for line in open(cfg_path, errors="ignore"):
        for spec in _SPEC.findall(line):
            if _MSG.search(spec):
                continue
            words = spec.split()
            if not words or not re.fullmatch(r"[\w.+\-]+", words[0]):
                continue
            terms = [(n, op, v) for n, op, v in _TERM.findall(spec)
                     if n == words[0]]
            if not terms:
                continue
            group = {}
            for _, op, ver in terms:
                group[op] = ver
            out.setdefault(words[0].lower(), []).append(group)
    return out


def constraints_path(root, rev):
    return os.path.join(root, "store", "facts",
                        "constraints.%s.json" % (rev or "unknown"))


def write_constraints(root, rev, constraints):
    os.makedirs(os.path.dirname(constraints_path(root, rev)), exist_ok=True)
    with open(constraints_path(root, rev), "w") as f:
        json.dump(constraints, f, indent=1, sort_keys=True)
        f.write("\n")


def _seg(x):
    # pkg-config versions carry non-numeric tails ("13+release",
    # "1.9.22git"); compare the leading digits of each segment
    m = re.match(r"\d+", x)
    return int(m.group()) if m else 0


def _cmp(a, b):
    av = [_seg(x) for x in a.split(".")]
    bv = [_seg(x) for x in b.split(".")]
    while len(av) < len(bv):
        av.append(0)
    while len(bv) < len(av):
        bv.append(0)
    return (av > bv) - (av < bv)


_OPS = {"<": lambda c: c < 0, "<=": lambda c: c <= 0,
        ">": lambda c: c > 0, ">=": lambda c: c >= 0,
        "=": lambda c: c == 0, "==": lambda c: c == 0}


def _satisfies(version, groups):
    return any(all(_OPS[op](_cmp(version, v)) for op, v in group.items())
               for group in groups)


def installed_version(ctx, name):
    r = subprocess.run(["pkg-config", "--modversion", name],
                       env=_strict_env(ctx), stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, text=True)
    return r.stdout.strip() or None


def _strict_env(ctx):
    from . import env as env_mod
    return env_mod.build_child_env(
        ctx["prefix"], strict_pkgconfig=True,
        tools_bin=os.path.join(ctx["tools_prefix"], "bin"))


def facts_path(root):
    return os.path.join(root, "store", "facts", "installed.json")


def backfill_installed(ctx, key, dep):
    """validate-time fact: the pkg-config version this port really
    shipped. Cheap, idempotent, feeds preflight."""
    if dep.get("tool"):
        return
    pc = dep.get("pc", key)
    ver = installed_version(ctx, pc)
    if not ver:
        return
    path = facts_path(ctx["root"])
    try:
        with open(path) as f:
            facts = json.load(f)
    except (OSError, ValueError):
        facts = {}
    slot = facts.setdefault(ctx["triplet"], {})
    if slot.get(pc) != ver:
        slot[pc] = ver
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(facts, f, indent=1, sort_keys=True)
            f.write("\n")


def preflight(root, triplet, constraints):
    """Compare configured intervals against installed versions.
    Returns (ok, [(name, interval, installed)] for violations)."""
    with open(facts_path(root)) as f:
        facts = json.load(f).get(triplet, {})
    bad = []
    checked = 0
    for name, groups in sorted(constraints.items()):
        ver = facts.get(name)
        if not ver:
            continue
        checked += 1
        if not _satisfies(ver, groups):
            interval = " | ".join(
                " ".join("%s%s" % (op, v) for op, v in sorted(g.items()))
                for g in groups)
            bad.append((name, interval, ver))
    return checked, bad
