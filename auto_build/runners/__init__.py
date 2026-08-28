"""L1 runner registry: build-system dispatch via deps.json 'system' field."""

from .base import BuildError, Runner
from .cmake import CmakeRunner
from .custom import CustomRunner
from .makefile import MakefileRunner
from .meson import MesonRunner
from .pip import PipRunner

_RUNNERS = {
    "makefile": MakefileRunner,
    "cmake": CmakeRunner,
    "meson": MesonRunner,
    "pip": PipRunner,
    "custom": CustomRunner,
}


def get_runner(system, ctx):
    cls = _RUNNERS.get(system)
    if not cls:
        raise BuildError("unknown build system '{}' (known: {})".format(
            system, sorted(_RUNNERS)))
    return cls(ctx)
