"""L1 runner registry: build-system dispatch via deps.json 'system' field."""

from .base import BuildError, Runner
from .makefile import MakefileRunner

_RUNNERS = {
    "makefile": MakefileRunner,
}


def get_runner(system, ctx):
    cls = _RUNNERS.get(system)
    if not cls:
        raise BuildError("unknown build system '{}' (known: {})".format(
            system, sorted(_RUNNERS)))
    return cls(ctx)
