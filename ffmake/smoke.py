"""Feature-driven smoke matrix, loaded from the knowledge base.

Cases live in ports/ffmpeg/check/smoke.toml, keyed by the FFmpeg
configure flag that enables the feature: a case runs only when the
built binary's configuration contains its flag. Kinds:
  encode      lavfi source -> encoder -> output file must be non-empty
  filter      lavfi source -> filter chain -> output file non-empty
  capability  feature listed in -encoders/-decoders/-filters output
  decode      input produced by an earlier case (alphabetical order)
"""

import os

import tomli


def load_cases(root):
    path = os.path.join(root, "ports", "ffmpeg", "check", "smoke.toml")
    with open(path, "rb") as f:
        return tomli.load(f)["case"]
