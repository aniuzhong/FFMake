"""Presentation layer: rich-rendered views with plain-text fallback.

Colors are on by default for terminals; pipes/CI/redirects degrade to
plain text automatically (rich Console detects non-TTY). Everything the
runners print is captured by the build view's live region -- the UI
renders state, the logs hold the detail.
"""

import sys
import threading
import time

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (Progress, SpinnerColumn, TextColumn,
                               TimeElapsedColumn)
    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False



def _real_stdout():
    """The real terminal stdout, unaffected by redirect_stdout captures."""
    return sys.__stdout__

def _pprint(text):
    """Print on the real terminal. UI output must survive the
    redirect_stdout capture the build verb wraps around its loop (runner
    chatter goes there; the view must not)."""
    print(text, file=_real_stdout(), flush=True)

def _secs(s):
    return "%dm%02ds" % (s // 60, s % 60)


# Heartbeat routing: run_with_heartbeat emits its liveness pings here.
# An active view installs a sink for the duration of the build loop -- the
# rich view absorbs them (its in-flight rows already show per-port elapsed
# time, and stray lines would fight the live region), the plain view
# reprints them on the real stdout (CI streams only stdout, and the
# build loop's capture buffer must not swallow the one signal that
# proves liveness). With no view installed the ping falls through to
# sys.stdout, so wrappers like the canary tee keep seeing it.
_heartbeat_sink = None


def set_heartbeat_sink(fn):
    global _heartbeat_sink
    _heartbeat_sink = fn


def heartbeat(label, elapsed):
    if _heartbeat_sink is not None:
        _heartbeat_sink(label, elapsed)
        return
    print("%s: still running (%ds elapsed)" % (label, int(elapsed)),
          flush=True)


class BuildView:
    """Closure build view: completed ports print as permanent lines while
    a transient region below shows one animated row per in-flight port
    (one row in serial builds, one per worker under --parallel). The
    console is bound to the real terminal, so the caller's stdout capture
    -- which keeps runner chatter off the screen -- cannot swallow the
    UI the way a default Console (which re-reads sys.stdout on every
    print) would."""

    def __init__(self, triplet, channel, total, plain=False):
        self.triplet = triplet
        self.channel = channel
        self.total = total
        self.done = 0
        self.failures = []          # (key, err, log)
        self.t0 = time.monotonic()
        self._lock = threading.Lock()
        self._starts = {}           # key -> monotonic start time
        self._tasks = {}            # key -> progress task id
        # rich live rendering is a TTY experience: on redirect/CI the
        # console is not a terminal and every refresh frame would be
        # printed -- one plain line per event instead
        self.plain = plain or not HAVE_RICH or not _real_stdout().isatty()
        if self.plain:
            self.console = None
            self._progress = None
        else:
            self.console = Console(file=_real_stdout())
            self._progress = Progress(
                SpinnerColumn(style="cyan"),
                TextColumn("[cyan]{task.fields[port]} · "
                           "{task.fields[backend]}[/cyan]"),
                TimeElapsedColumn(),
                console=self.console,
                transient=True,
                refresh_per_second=4,
                # the caller owns stdout capture (runner chatter);
                # a second redirect here would fight it
                redirect_stdout=False, redirect_stderr=False)

    def __enter__(self):
        if self._progress:
            self._progress.start()
        set_heartbeat_sink(self._heartbeat)
        return self

    def __exit__(self, *exc):
        if self._progress:
            self._progress.stop()
        set_heartbeat_sink(None)
        return False

    def _heartbeat(self, label, elapsed):
        if not self.plain:
            return
        _pprint("%s: still running (%ds elapsed)" % (label, int(elapsed)))

    def _retire(self, key):
        if not self._progress:
            return
        tid = self._tasks.pop(key, None)
        if tid is not None:
            self._progress.remove_task(tid)

    def port_start(self, key, backend):
        with self._lock:
            self._starts[key] = time.monotonic()
        if self.plain:
            return
        self._tasks[key] = self._progress.add_task(
            "", port=key, backend=backend)

    def port_done(self, key, backend):
        with self._lock:
            self.done += 1
            start = self._starts.pop(key, None)
        secs = time.monotonic() - start if start is not None else 0.0
        if self.plain:
            _pprint("[ffmake] ✓ %-18s %s" % (key, _secs(secs)))
            return
        self._retire(key)
        self.console.print("  [green]✓[/green] %-18s %s" % (key, _secs(secs)))

    def port_fail(self, key, backend, err, log):
        with self._lock:
            self.failures.append((key, err, log))
        if self.plain:
            _pprint("[ffmake] ✗ %s: %s" % (key, err))
            return
        self._retire(key)
        self.console.print("[red]✗ %s[/red] %s" % (key, err))

    def note(self, text):
        """A one-off line outside the per-port rhythm (mode notices)."""
        if self.plain:
            _pprint(text)
        else:
            self.console.print(text)

    def report(self):
        """Abort post-mortem: one block per failed port -- the error and,
        when the runner attached one, the stage-log tail. Rendered on the
        real terminal so it survives the caller's stdout capture."""
        if not self.failures:
            return
        for key, err, log in self.failures:
            tail = getattr(err, "tail", None)
            if self.plain:
                _pprint("✗ %s: %s\n    log: %s" % (key, err, log))
                if tail:
                    _pprint(tail)
            elif tail:
                self.console.print(Panel(
                    tail, title="✗ %s" % key, expand=False,
                    border_style="red"))
            else:
                self.console.print("[red]✗ %s[/red] %s\n    log: %s"
                                   % (key, err, log))

    def finish(self):
        secs = _secs(time.monotonic() - self.t0)
        line = ("✓ closure complete  %d/%d  %s"
                % (self.done, self.total, secs))
        if self.plain:
            _pprint("[ffmake] " + line)
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
