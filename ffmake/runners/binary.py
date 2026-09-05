"""binary runner: pinned prebuilt artifacts as ports.

Presence-based: the check binary existing under the install dir IS the
stamp (re-extraction of a verified tarball cannot improve on it). The
distfile itself is content-addressed and sha256-verified like any other
source, so provisioning stays byte-identical everywhere.
"""

import os
import shutil
import tarfile
import tempfile

from .base import BuildError, Runner


class BinaryRunner(Runner):
    system = "binary"

    def _check_path(self, key, dep):
        # tool_bin is the full path under the tools prefix; install_dir
        # only decides where the archive unpacks
        return os.path.join(self.install_prefix(dep),
                            dep.get("tool_bin", "bin/" + key))

    def up_to_date(self, key, dep):
        return os.path.exists(self._check_path(key, dep))

    def build(self, key, dep):
        if self.up_to_date(key, dep):
            print("dep {}: present, skip".format(key))
            return
        source = dep.get("source") or {}
        if source.get("type") != "tar":
            raise BuildError("binary {}: needs a pinned tar source".format(
                key))
        dist = self.distfile_path(source)
        if not os.path.exists(dist):
            raise BuildError(
                "binary {}: distfile {} missing -- provisioning happens "
                "via the build verb (or run 'ffmake build')".format(
                    key, dist))
        digest = self._sha256(dist)
        if source.get("sha256") and digest != source["sha256"]:
            raise BuildError("binary {}: distfile sha256 mismatch".format(
                key))
        prefix = self.install_prefix(dep)
        os.makedirs(prefix, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            with tarfile.open(dist) as tf:
                tf.extractall(tmp)
            roots = [os.path.join(tmp, n) for n in os.listdir(tmp)]
            if len(roots) != 1 or not os.path.isdir(roots[0]):
                raise BuildError("binary {}: archive root layout "
                                 "unexpected".format(key))
            dest = prefix
            if dep.get("install_dir"):
                dest = os.path.join(prefix, dep["install_dir"])
            os.makedirs(dest, exist_ok=True)
            for item in os.listdir(roots[0]):
                s = os.path.join(roots[0], item)
                d = os.path.join(dest, item)
                if os.path.isdir(s) and not os.path.islink(s):
                    shutil.copytree(s, d, symlinks=True, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
        if not self.up_to_date(key, dep):
            raise BuildError("binary {}: check binary missing after "
                             "install: {}".format(key,
                                                  self._check_path(key,
                                                                   dep)))
        print("dep {}: provisioned -> {}".format(
            key, self._check_path(key, dep)))
