#!/usr/bin/env python3
"""Sole entry: python3 ffmake.py <configure|build|install|test|all|probe|init>"""

import sys

if sys.version_info[0] < 3:
    sys.stderr.write(
        "error: python3 is required, but got python %d.%d\n"
        "tip: run `python3 ffmake.py ...` (this box maps /usr/bin/python "
        "to python2)\n" % (sys.version_info[0], sys.version_info[1]))
    sys.exit(1)

import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ffmake.cli import main

if __name__ == "__main__":
    sys.exit(main())
