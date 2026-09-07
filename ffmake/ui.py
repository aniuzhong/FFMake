"""Presentation layer: rich-rendered views with plain-text fallback.

Colors are on by default for terminals; pipes/CI/redirects degrade to
plain text automatically (rich Console detects non-TTY). Everything the
runners print is captured by the build view's live region -- the UI
renders state, the logs hold the detail.
"""

import sys
import time

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (BarColumn, MofNCompleteColumn, Progress,
                               SpinnerColumn, TextColumn, TimeElapsedColumn)
    from rich import box
    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False



def _real_stdout():
    """The real terminal stdout, unaffected by redirect_stdout captures."""
    import sys
    return sys.__stdout__

def _secs(s):
    return "%dm%02ds" % (s // 60, s % 60)


class BuildView:
    """Closure build view built on Console.status: the spinner row shows
    the in-flight port while completed ports scroll above it as plain
    lines -- print and status coexist without stdout capture."""

    def __init__(self, triplet, channel, total, plain=False):
        import sys
        self.triplet = triplet
        self.channel = channel
        self.total = total
        self.done = 0
        self.failures = []          # (key, err, log)
        self.t0 = time.monotonic()
        # rich live rendering is a TTY experience: on redirect/CI the
        # console is not a terminal and every refresh frame would be
        # printed -- one plain line per event instead
        self.plain = plain or not HAVE_RICH or not sys.__stdout__.isatty()
        self.console = None if self.plain else Console()
        self._cm = None

    def __enter__(self):
        return self

    def _touch(self, key=None, backend=None):
        if self._cm:
            self._cm.update(
                "[cyan]⟳ %s · %s[/cyan]   %d/%d"
                % (key or "", backend or "", self.done, self.total))

    def port_start(self, key, backend):
        self._touch(key, backend)

    def port_done(self, key, backend, secs):
        self.done += 1
        if self.plain:
            print("[ffmake] ✓ %-18s %s" % (key, _secs(secs)), flush=True)
            return
        self.console.print("  [green]✓[/green] %-18s %s"
                           % (key, _secs(secs)))
        self._touch(key, backend)

    def port_fail(self, key, backend, err, log):
        self.failures.append((key, str(err), log))
        if self.plain:
            print("[ffmake] ✗ %s: %s" % (key, err), flush=True)
            return
        self.console.print("[red]✗ %s[/red] %s" % (key, err))

    def __exit__(self, *exc):
        if self._cm:
            self._cm.__exit__(None, None, None)
        return False

    def finish(self):
        secs = _secs(time.monotonic() - self.t0)
        line = ("✓ closure complete  %d/%d  %s"
                % (self.done, self.total, secs))
        if self.plain:
            print("[ffmake] " + line, flush=True)
        else:
            self.console.print("[green]" + line + "[/green]")


def smoke_line(name, status, detail=""):
    """One smoke row: status in {'PASS','FAIL','SKIP'}."""
    glyph, color = {"PASS": ("✓", "green"), "FAIL": ("✗", "red"),
                    "SKIP": ("─", "dim")}.get(status, ("·", ""))
    text = "  %s %-18s %-5s %s" % (glyph, name, status, detail)
    if HAVE_RICH:
        Console().print(
            "[{c}]{g}[/] {n:<18} [{c}]{s}[/] {d}".format(
                c=color, g=glyph, n=name, s=status, d=detail))
    else:
        print(text)


def smoke_summary(passed, failed, skipped, total):
    line = "summary: %d passed · %d failed · %d skipped · %d total" % (
        passed, failed, skipped, total)
    if HAVE_RICH:
        color = "green" if failed == 0 else "red"
        Console().print("[%s]%s[/]" % (color, line))
    else:
        print(line)


def plan_summary(triplet, channel, ports, blocked, unmapped):
    if HAVE_RICH:
        Console().print(
            "plan: [green]%s[/green] [cyan]%s[/cyan] -> %d ports "
            "(blocked %d, unmapped %d)" % (triplet, channel, ports,
                                           blocked, unmapped))
    else:
        print("plan: %s [%s] -> %d ports (blocked %d, unmapped %d)" % (
            triplet, channel, ports, blocked, unmapped))


def failure_report(key, err, log):
    if HAVE_RICH:
        Console().print(Panel(
            "stage log:\n%s" % log, title="✗ %s" % key, expand=False,
            border_style="red"))
    else:
        print("✗ %s: %s\n  log: %s" % (key, err, log))
