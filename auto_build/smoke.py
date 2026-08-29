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
        # full AV1 decode smoke below (libdav1d-decode) needs the svtav1
        # encode case to run first and produce its input
    },
    {
        "flag": "--enable-libsvtav1",
        "name": "libsvtav1-encode",
        "kind": "encode",
        "encoder": "libsvtav1",
        "input": "testsrc2=duration=0.5:size=640x360:rate=30",
        "ext": "mkv",
    },
    {
        "flag": "--enable-libdav1d",
        "name": "libdav1d-decode",
        "kind": "decode",
        "decoder": "libdav1d",
        # produced by libsvtav1-encode above (alphabetical case order)
        "input_file": "libsvtav1-encode.mkv",
    },
    {
        "flag": "--enable-libaom",
        "name": "libaom-encode",
        "kind": "encode",
        "encoder": "libaom-av1",
        "input": "testsrc2=duration=0.3:size=320x180:rate=30",
        "ext": "mkv",
    },
    {
        "flag": "--enable-libvpx",
        "name": "libvpx-vp9-encode",
        "kind": "encode",
        "encoder": "libvpx-vp9",
        "input": "testsrc2=duration=0.5:size=640x360:rate=30",
        "ext": "webm",
    },
    {
        "flag": "--enable-libmp3lame",
        "name": "libmp3lame-encode",
        "kind": "encode",
        "stream": "a",
        "encoder": "libmp3lame",
        "input": "sine=duration=0.5:sample_rate=44100",
        "ext": "mp3",
    },
    {
        "flag": "--enable-libopus",
        "name": "libopus-encode",
        "kind": "encode",
        "stream": "a",
        "encoder": "libopus",
        "input": "sine=duration=0.5:sample_rate=48000",
        "ext": "opus",
    },
    {
        "flag": "--enable-libvorbis",
        "name": "libvorbis-encode",
        "kind": "encode",
        "stream": "a",
        "encoder": "libvorbis",
        "input": "sine=duration=0.5:sample_rate=44100",
        "ext": "ogg",
    },
]
