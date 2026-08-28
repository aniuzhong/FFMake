"""Feature-driven smoke matrix (phase 4).

Cases are keyed by the FFmpeg configure flag that enables the feature; a
case runs only when the built binary's configuration contains its flag.
Kinds:
  encode      lavfi source -> encoder -> output file must be non-empty
  filter      lavfi source -> filter chain -> output file must be non-empty
  capability  feature listed in -encoders/-decoders/-filters output (no
              data path; for decoder-only libs whose input we cannot
              produce yet, e.g. libdav1d before an AV1 encoder port exists)

Adding a port in phase 5: add one dict here. Keep cases fast (sub-second
lavfi inputs) and side-effect free (outputs go to the smoke dir).
"""

CASES = [
    {
        "flag": "--enable-libx264",
        "name": "libx264-encode",
        "kind": "encode",
        "encoder": "libx264",
        "input": "testsrc2=duration=0.5:size=640x360:rate=30",
        "ext": "mp4",
    },
    {
        "flag": "--enable-libx265",
        "name": "libx265-encode",
        "kind": "encode",
        "encoder": "libx265",
        "input": "testsrc2=duration=0.5:size=640x360:rate=30",
        "ext": "mp4",
    },
    {
        "flag": "--enable-libzimg",
        "name": "zscale-16bit",
        "kind": "filter",
        # zimg needs labeled colorspace to pick a conversion path (lessons #25)
        "filter": ("setparams=colorspace=bt709:color_primaries=bt709:"
                   "color_trc=bt709,zscale=transfer=linear,"
                   "format=yuv444p10,zscale=transfer=bt709"),
        "input": "testsrc2=duration=0.5:size=640x360:rate=30",
        "ext": "png",
    },
    {
        "flag": "--enable-libdav1d",
        "name": "libdav1d-embed",
        "kind": "capability",
        "list": "decoders",
        "needle": "libdav1d",
        # real AV1 decode smoke lands when an AV1 encoder port (libsvtav1)
        # exists to produce the input
    },
]
