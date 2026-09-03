"""FFMake: FFmpeg auto build system.

Layers:
  env       build child-process environment whitelist (isolation base)
  runners   autotools / cmake / meson / makefile / custom
  fixups    runner-level generic fixes + per-library hooks
  deps.json dependency knowledge base (pure data)
  loop      FFmpeg configure error-driven closed loop
"""

__version__ = "0.1.0"
