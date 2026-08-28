"""ffmpeg-auto-build: full-source FFmpeg build system.

Layers:
  L0 env       build child-process environment whitelist (isolation base)
  L1 runners   autotools / cmake / meson / makefile / custom
  L2 fixups    runner-level generic fixes + per-library hooks
  L3 deps.json dependency knowledge base (pure data)
  L4 loop      FFmpeg configure error-driven closed loop

Current phase: 0 (skeleton + L0).
"""

__version__ = "0.1.0"
