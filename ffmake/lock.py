"""L3.5: lock.json — the resolved-closure snapshot (Cargo.lock analog).

Written automatically after a successful `configure` for a triplet, merged
across triplets into one file at the repo root (tracked in git, like
Cargo.lock). Records, per triplet:
  - every port of the closure: as-resolved recipe + the resolved full git
    commit (branches/tags move, hashes do not — vcpkg baseline philosophy)
  - the FFmpeg source tree resolved rev (master drifts; the lock does not)
  - the pass-through flags in effect
and a global "tools" section for host tools.

This is not a verb: it is configure's side effect. `port install` does not
touch it (dev/repair action, not closure convergence).
"""

import json
import os
import subprocess

from . import paths


def _git_rev(path):
    """Full HEAD hash of a git tree, or None.

    Guard: rev-parse walks UP to the nearest .git, which would wrongly
    report the ffmake repo's own commit for archive-exported (git-less)
    trees. Only trust a .git that lives in the tree itself.
    """
    if not os.path.exists(os.path.join(path, ".git")):
        return None
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True)
        return r.stdout.strip() or None
    except OSError:
        return None


def _runner_for(ctx, dep):
    from .runners import get_runner
    return get_runner(dep.get("system", "makefile"), ctx)


def _port_entry(ctx, key, dep):
    runner = _runner_for(ctx, dep)
    stamp = runner.read_stamp(key, dep)
    entry = {
        "recipe": dep,
        "stamp_hash": (stamp or {}).get("hash"),
    }
    source = dep.get("source") or {}
    if source.get("type") == "git":
        src = os.path.join(paths.src(ctx["root"]), key)
        entry["resolved_commit"] = _git_rev(src)
    return entry


def write_lock(ctx, data, deps, built):
    root = ctx["root"]
    lock_path = paths.lock_file(root)
    lock = {}
    if os.path.exists(lock_path):
        try:
            with open(lock_path) as f:
                lock = json.load(f)
        except ValueError:
            lock = {}
    lock["schema"] = 1
    lock.setdefault("tools", {})
    for key, dep in sorted(deps.items()):
        if dep.get("tool"):
            lock["tools"][key] = _port_entry(ctx, key, dep)

    triplet = ctx["triplet"]
    lock.setdefault("triplets", {})
    lock["triplets"][triplet] = {
        "ffmpeg": {
            "url": ((data.get("ffmpeg") or {}).get("source") or {}).get("url"),
            "resolved_rev": _git_rev(paths.ffmpeg_src_dir(root)),
            "flags": ctx.get("flags", []),
        },
        "ports": {key: _port_entry(ctx, key, deps[key])
                  for key in sorted(deps) if not deps[key].get("tool")},
        "last_built": sorted(built),
    }
    with open(lock_path, "w") as f:
        json.dump(lock, f, indent=2, sort_keys=True)
        f.write("\n")
    print("lock: wrote {}".format(lock_path))
