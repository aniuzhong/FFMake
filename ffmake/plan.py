"""L4 planner: demanded closure from the model + ffmpeg's configure source.

Replaces error-driven discovery. Demands come from two channels:
  (a) names harvested out of configure's check/require calls that sit in
      the lexical scope of an enabled feature (brace blocks, if/fi, `&&`
      continuations, sub-options);
  (b) the feature-name fallback: an enabled feature with a same-named
      port (frei0r, amf, sdl2, ...) is a demand -- header-checked and
      autodetect features have no pkg-config line to harvest.
The closure then closes over needs with per-triplet overrides and
platform filters applied, in topological build order.
"""

import json
import os
import re

_FUNC = re.compile(
    r'\b(require2?|require_pkg_config2?|check_lib2?|check_pkg_config|'
    r'test_lib2?|test_pkg_config|check_cpp_condition|test_cpp_condition|'
    r'require_headers|check_headers)\s+'
    r'(?:"([^"]*)"\s*|([\w.+-]+)\s*)(?:"([^"]*)"\s*|([\w.+-]+))?')
_PKG_FUNCS = {"require_pkg_config", "require_pkg_config2",
              "check_pkg_config", "test_pkg_config"}
_EN = re.compile(r"\benabled\s+([a-z0-9_\-]+)")
_NAME = re.compile(r"^[a-zA-Z][\w+.\-]*$")
FAMILY = {"linux-x86_64": "linux", "mingw-x86_64-llvm": "mingw"}


def configure_path(root):
    """The root product's configure -- the constraint oracle. Must be
    seeded (cold seed or `ffmake upgrade`); planning never reads foreign
    trees."""
    from . import paths
    return os.path.join(paths.ffmpeg_src_dir(root), "configure")


def _harvest(line):
    names = set()
    for m in _FUNC.finditer(line):
        func = m.group(1)
        toks = [m.group(3)]
        if func in _PKG_FUNCS:
            toks += [m.group(2), m.group(5)]
        for tok in toks:
            if tok:
                name = tok.split()[0]
                if _NAME.match(name) and name.lower() != "version":
                    names.add(name)
    return names


def _extract_demands(cfg_path, features):
    demands = {}
    depth = 0
    frames = []  # [kind, open_depth, feats]

    def feats_on(line):
        out = set()
        for m in _EN.findall(line):
            for cand in (m, m.replace("_", "-")):
                if cand in features:
                    out.add(cand)
                    break
        return out

    for line in open(cfg_path, errors="ignore"):
        line = line.rstrip("\n")
        s = line.strip()
        opens, closes = line.count("{"), line.count("}")
        depth += opens - closes
        while frames and frames[-1][0] == "brace" and depth < frames[-1][1]:
            frames.pop()
        if s == "fi" or s.endswith("; fi"):
            for i in range(len(frames) - 1, -1, -1):
                if frames[i][0] == "fi":
                    frames.pop(i)
                    break

        active = set()
        for kind, d, feats in frames:
            active |= feats
        active |= feats_on(line)
        names = _harvest(line)
        for f in active:
            demands.setdefault(f, set()).update(names)

        net = opens - closes
        single_line_block = opens and closes and net == 0
        cont = s.endswith("&&") or s.endswith("||")
        frames = [fr for fr in frames if fr[0] != "cont"]
        if cont:
            guard = feats_on(line)
            if guard:
                frames.append(["cont", depth, guard])
        if net > 0 and not single_line_block:
            guard = feats_on(line)
            if guard:
                frames.append(["brace", depth, guard])
        elif "; then" in s and " enabled " in line:
            guard = feats_on(line)
            if guard:
                frames.append(["fi", depth, guard])
    return demands


def _provides_index(uni):
    index = {}
    for key, dep in uni.items():
        names = {key, dep.get("pc", key)}
        names |= set(dep.get("match_names", []))
        names |= set(dep.get("pcs", []))
        for n in names:
            index.setdefault(n.lower(), key)
    return index


def direct_ports(uni, features, cfg_path):
    index = _provides_index(uni)
    demands = _extract_demands(cfg_path, features)
    direct, unmapped = set(), {}
    for feat, names in sorted(demands.items()):
        for n in names:
            key = index.get(n.lower())
            if key:
                direct.add(key)
            else:
                unmapped.setdefault(n, set()).add(feat)
    for feat in features:
        if feat in uni:
            direct.add(feat)
        elif feat.startswith("lib") and feat[3:] in uni:
            direct.add(feat[3:])
        elif "lib" + feat in uni:
            direct.add("lib" + feat)
    return direct, unmapped


def closure(uni, direct, triplet):
    """Topologically ordered planned ports + platform-blocked set."""
    fam = FAMILY.get(triplet, triplet.split("-")[0])
    order, seen, blocked = [], set(), set()
    visiting = set()

    def visit(key):
        if key in seen or key in blocked:
            return
        if key in visiting:
            raise SystemExit("plan: dependency cycle at " + key)
        dep = uni.get(key)
        if dep is None:
            return
        plat = dep.get("platforms")
        if plat and triplet not in plat and fam not in plat:
            blocked.add(key)
            return
        visiting.add(key)
        ov = dep.get("triplet_overrides", {}).get(triplet, {})
        for n in ov.get("needs", dep.get("needs", [])):
            visit(n)
        visiting.discard(key)
        seen.add(key)
        order.append(key)

    for key in sorted(direct):
        visit(key)
    return order, blocked


def compute(root, triplet, uni, cfg_path, system_tier=()):
    """system_tier: ports the host system satisfies on this triplet
    (profiles/system-tier.json). They must never enter the plan --
    demanding them would change ffmpeg's linkage and diverge from the
    reference artifact. Needs-closure still builds them if some kept
    port genuinely requires them."""
    from . import model
    flags = model.load_flags(root, triplet)
    features = {f[len("--enable-"):] for f in flags
                if f.startswith("--enable-")}
    direct, unmapped = direct_ports(uni, features, cfg_path)
    direct -= set(system_tier)
    order, blocked = closure(uni, direct, triplet)
    return {
        "schema": 1,
        "triplet": triplet,
        "features": {f: "policy" for f in features},
        "direct": sorted(direct),
        "order": order,
        "blocked": sorted(blocked),
        "unmapped": {n: sorted(s) for n, s in sorted(unmapped.items())},
    }


def plan_path(root, channel, triplet):
    return os.path.join(root, "plans", channel, "%s.plan.json" % triplet)


def write(root, channel, triplet, plan):
    path = plan_path(root, channel, triplet)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(plan, f, indent=1, sort_keys=True)
        f.write("\n")
    return path
