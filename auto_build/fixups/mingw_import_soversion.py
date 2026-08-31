"""mingw_import_soversion fixup: alias SOVERSIONed import libraries.

Some cmake projects embed the SOVERSION into the PE import library name
(e.g. rabbitmq-c -> librabbitmq.4.dll.a) while consumers link plain
-l<name>, which only resolves lib<name>.dll.a / lib<name>.a. Copy every
versioned import lib to its plain name (when missing). Idempotent.
"""

import glob
import os
import re
import shutil


def run(ctx, key, dep):
    lib = os.path.join(ctx["prefix"], "lib")
    aliased = 0
    for imp in glob.glob(os.path.join(lib, "*.dll.a")):
        m = re.match(r"^(lib.+)\.[0-9]+\.dll\.a$", os.path.basename(imp))
        if not m:
            continue
        dst = os.path.join(lib, m.group(1) + ".dll.a")
        if not os.path.exists(dst):
            shutil.copy2(imp, dst)
            aliased += 1
    if aliased:
        print("fixup mingw_import_soversion: {} alias(es) in {}".format(
            aliased, lib))
