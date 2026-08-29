"""makefile runner: classic ./configure && make && make install projects.

Out-of-tree per-port builds (vcpkg buildtrees style): vendor src/ stays
pristine, the build tree lives in workspace/build/<ns>/<key>/ with
colocated logs. Cross triplets get --host/--cross-prefix injected.
Git sources without a pre-generated configure declare "autogen": a shell
command (placeholders {src}/{bdir}/{tools}/{prefix}) run inside src/ first.
"""

import os

from .base import Runner


class MakefileRunner(Runner):
    system = "makefile"

    def build(self, key, dep):
        if self.up_to_date(key, dep):
            print("dep {}: up to date, skip".format(key))
            return
        prefix = self.install_prefix(dep)
        src, bdir, logs = self.prepare(key, dep)
        if dep.get("prefixup"):
            # pre-build source repair (e.g. strip unbuildable tool programs
            # from Makefile.in before configure consumes it)
            self.run(["bash", "-c", self._subst(dep["prefixup"], src, bdir,
                                                prefix)],
                     src, os.path.join(logs, "prefixup.log"),
                     env=self.env(strict=False))
        if dep.get("autogen"):
            # git trees ship configure.ac only; generate configure in src/.
            # aclocal must also see the tools sysroot's m4 macros (libtool
            # lives there, not in /usr) -> ACLOCAL_PATH injection.
            extra = {"ACLOCAL_PATH": ":".join([
                os.path.join(self.ctx["tools_prefix"], "share", "aclocal"),
                "/usr/share/aclocal"])}
            self.run(["bash", "-c",
                      self._subst(dep["autogen"], src, bdir, prefix)],
                     src, os.path.join(logs, "autogen.log"),
                     env=self.env(extra=extra))
        # joined --prefix=... form: required by FFmpeg, safest everywhere;
        # configure_name covers OpenSSL-style "Configure" spellings.
        # strict_pkgconfig:false opts a port into system .pc visibility
        # (e.g. libxcb needs system xau/xdmcp dev files).
        strict = bool(dep.get("strict_pkgconfig", True))
        configure = dep.get("configure_name", "configure")
        args = [os.path.join(os.path.abspath(src), configure),
                "--prefix=" + prefix] + \
               list(dep.get("configure_args", [])) + self.cross_args()
        self.run(args, bdir, os.path.join(logs, "configure.log"),
                 env=self.env(strict=strict))
        self.run(["make", "-j", str(self.ctx["jobs"])], bdir,
                 os.path.join(logs, "make.log"), env=self.env(strict=strict))
        self.run(["make", dep.get("install_target", "install")], bdir,
                 os.path.join(logs, "install.log"),
                 env=self.env(strict=strict))
        self.write_stamp(key, dep)
        print("dep {}: built & installed -> {}".format(key, prefix))

    def _subst(self, cmd, src, bdir, prefix):
        return cmd.format(
            src=os.path.abspath(src),
            bdir=os.path.abspath(bdir),
            tools=self.ctx["tools_prefix"],
            prefix=prefix)
