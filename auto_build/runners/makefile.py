"""makefile runner: classic ./configure && make && make install projects.

Out-of-tree per-port builds (vcpkg buildtrees style): vendor src/ stays
pristine, the build tree lives in workspace/build/<ns>/<key>/ with
colocated logs. Cross triplets get --host/--cross-prefix injected.
Git sources without a pre-generated configure declare "autogen": a shell
command (placeholders {src}/{bdir}/{tools}/{prefix}) run inside src/ first.
"""

import glob
import os

from .. import paths
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
        alias = paths.sysroot_alias(self.ctx["root"], self.ctx["triplet"])
        subst = {"alias": alias, "prefix": prefix,
                 "src": os.path.abspath(src), "bdir": os.path.abspath(bdir),
                 "tools": self.ctx["tools_prefix"]}
        # placeholder support for args like --with-libiconv-prefix={prefix}
        cfg_args = [a.format(**subst) if "{" in a else a
                    for a in dep.get("configure_args", [])]
        args = [os.path.join(os.path.abspath(src), configure),
                "--prefix=" + prefix] + cfg_args + self.cross_args(dep)
        # cross: make the target sysroot headers visible. autoconf captures
        # CPPFLAGS into the generated Makefile, which covers ports that
        # assume default-path headers (native keeps its proven env). The
        # triplet's cc_suffix (posix threads) rides along via CC/CXX --
        # --host alone would resolve to the default (win32) variant.
        extra = None
        if self.ctx["triplet_cfg"]["cross_prefix"]:
            alias_inc = paths.sysroot_alias(
                self.ctx["root"], self.ctx["triplet"]) + "/include"
            alias_lib = paths.sysroot_alias(
                self.ctx["root"], self.ctx["triplet"]) + "/lib"
            sfx = self.ctx["triplet_cfg"].get("cc_suffix", "")
            xp = self.ctx["triplet_cfg"]["cross_prefix"]
            # NOTE: no cross_ldflags here -- libtool parses bare -l flags
            # in env LDFLAGS as inter-library deps and drops to static-only
            # when no shared candidate exists. The cross_ldflags merge only
            # targets make_args LDFLAGS= overrides (libtool C++ DLL mode).
            extra = {"CPPFLAGS": "-I" + alias_inc + " -U_FORTIFY_SOURCE",
                     "LDFLAGS": "-L" + alias_lib,
                     "CC": xp + "gcc" + sfx, "CXX": xp + "g++" + sfx}
        self.run(args, bdir, os.path.join(logs, "configure.log"),
                 env=self.env(strict=strict, extra=extra))
        # per-port make-time overrides, e.g. libtool mingw DLL builds need
        # LDFLAGS=-no-undefined (libtool refuses shared libs without it,
        # silently falling back to static-only installs). {alias} expands
        # to the ASCII alias sysroot root.
        # A triplet's cross_ldflags is merged into any LDFLAGS= override
        # (make command-line vars replace env, so env-only injection would
        # be lost exactly for the ports that need it most).
        _xld = self.ctx["triplet_cfg"].get("cross_ldflags")
        if _xld and "{clang_rt}" in _xld:
            hits = glob.glob(os.path.join(
                os.path.dirname(self.cross_bin()),
                "lib", "clang", "*", "lib", "windows",
                "libclang_rt.builtins-x86_64.a"))
            if hits:
                _xld = _xld.replace("{clang_rt}", hits[0])
            else:
                _xld = None
        # cross links must see the target sysroot: make_args LDFLAGS= vars
        # replace env LDFLAGS entirely, so re-add -L (and the triplet's
        # cross_ldflags, e.g. compiler-rt builtins for llvm-mingw) here.
        if self.ctx["triplet_cfg"]["cross_prefix"]:
            alias_lib = paths.sysroot_alias(
                self.ctx["root"], self.ctx["triplet"]) + "/lib"
        else:
            alias_lib = None
        make_args = []
        for a in dep.get("make_args", []):
            if a.startswith("LDFLAGS=") and "sysroot" not in a:
                a = a.format(**subst)
                if alias_lib and "-L" not in a:
                    a = a + " -L" + alias_lib
                if _xld and "clang_rt" not in a:
                    a = a + " " + _xld
                make_args.append(a)
                continue
            make_args.append(a.format(**subst))
        self.run(["make", "-j", str(self.ctx["jobs"])] + make_args, bdir,
                 os.path.join(logs, "make.log"),
                 env=self.env(strict=strict, extra=extra))
        self.run(["make", dep.get("install_target", "install")] + make_args,
                 bdir, os.path.join(logs, "install.log"),
                 env=self.env(strict=strict, extra=extra))
        self.write_stamp(key, dep)
        print("dep {}: built & installed -> {}".format(key, prefix))

    def _subst(self, cmd, src, bdir, prefix):
        return cmd.format(
            src=os.path.abspath(src),
            bdir=os.path.abspath(bdir),
            tools=self.ctx["tools_prefix"],
            prefix=prefix)
