"""L2 per-port fixup hooks (vcpkg "packages staging fix" analog).

Applied after a port's build/install and before validation. Each fixup is
a module in this package exposing run(ctx, key, dep); ports opt in via
deps.json "fixups": ["name"]. Keep this list small: prefer runner-level
generic fixes; a fixup is the last resort for a port-specific install bug.
"""

import importlib

_REGISTRY = {}


def _load(name):
    if name not in _REGISTRY:
        _REGISTRY[name] = importlib.import_module(
            "ffmake.fixups." + name)
    return _REGISTRY[name]


def apply(ctx, key, dep):
    for name in dep.get("fixups", []):
        _load(name).run(ctx, key, dep)
