"""L1 runner registry: build-system dispatch via deps.json 'system' field."""

from .base import BuildError, Runner
from .binary import BinaryRunner
from .cmake import CmakeRunner
from .custom import CustomRunner
from .makefile import MakefileRunner
from .meson import MesonRunner
from .pip import PipRunner
from .system_pc import SystemPcRunner

_RUNNERS = {
    "makefile": MakefileRunner,
    "binary": BinaryRunner,
    "cmake": CmakeRunner,
    "meson": MesonRunner,
    "pip": PipRunner,
    "custom": CustomRunner,
    "system-pc": SystemPcRunner,
}


def get_runner(system, ctx):
    cls = _RUNNERS.get(system)
    if not cls:
        raise BuildError("unknown build system '{}' (known: {})".format(
            system, sorted(_RUNNERS)))
    return cls(ctx)
