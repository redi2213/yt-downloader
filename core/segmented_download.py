"""Downloading one file in several pieces at the same time (like a download manager).

``fetch(url, path, ...)`` asks the server for the size and whether it accepts byte ranges
(``Range: bytes=a-b``). If it does, the file is cut into pieces that are fetched at the same
time and written at their own place in ``path``; a piece that fails is asked again from where it
stopped, so Pause / Resume and a dropped connection cost nothing. A server without ranges is
read in one go (and cannot be resumed after a drop).

Before the first byte the empty file can be created at its final size (``preallocate``):
on Android with Java's ``RandomAccessFile.setLength()``, elsewhere ``truncate``.
No Kivy in here.
"""
import os
import threading
import time

import requests

CHUNK = 128 * 1024
MIN_SEGMENT = 1024 * 1024          # a piece is never smaller than this
RETRIES = 5


class Cancelled(Exception):
    """The download was stopped by the user."""


class Control:
    """Pause / Resume / Stop for one download, shared with its threads."""

    def __init__(self):
        self._run = threading.Event()
        self._run.set()
        self.cancelled = False

    @property
    def paused(self):
        return not self._run.is_set() and not self.cancelled

    def pause(self):
        self._run.clear()

    def resume(self):
        self._run.set()

    def cancel(self):
        self.cancelled = True
        self._run.set()

    def check(self):
        if self.cancelled:
            raise Cancelled()

    def wait_while_paused(self):
        while not self._run.is_set():
            self._run.wait(0.4)
        self.check()


def probe(url, headers=None):
    """``(total bytes or 0, server accepts ranges)``."""
    h = dict(headers or {})
    h["Range"] = "bytes=0-0"
    with requests.get(url, headers=h, stream=True, timeout=(15, 30)) as r:
        if r.status_code == 206:
            tail = r.headers.get("Content-Range", "").rsplit("/", 1)[-1]
            total = int(tail) if tail.isdigit() else 0
            return total, bool(total)
        r.raise_for_status()
        return int(r.headers.get("Content-Length") or 0), False


def preallocate_file(path, total):
    """Creates ``path`` at its final size. Returns the way it was done (for the log)."""
    try:
        from jnius import autoclass
        raf = autoclass("java.io.RandomAccessFile")(path, "rw")
        try:
            raf.setLength(int(total))
        finally:
            raf.close()
        return "RandomAccessFile.setLength"
    except Exception:
        with open(path, "wb") as f:
            f.truncate(int(total))
        return "truncate"


def plan(total, wanted):
    """[(start, end)] inclusive byte ranges: ``wanted`` pieces, none under MIN_SEGMENT."""
    n = max(1, min(int(wanted), total // MIN_SEGMENT)) if total else 1
    size = total // n
    return [(i * size, total - 1 if i == n - 1 else (i + 1) * size - 1) for i in range(n)]


def fetch(url, path, headers=None, segments=4, preallocate=True, control=None, on_progress=None):
    """Downloads ``url`` into ``path``. Raises ``Cancelled`` when stopped."""
    control = control or Control()
    total, ranges_ok = probe(url, headers)
    control.check()
    if not ranges_ok or not total:
        return _single(url, path, headers, total, control, on_progress)

    if preallocate:
        preallocate_file(path, total)
    else:
        open(path, "wb").close()

    parts = plan(total, segments)
    pos = [a for a, _b in parts]
    lock = threading.Lock()
    errors = []
    abort = threading.Event()

    def worker(i):
        end = parts[i][1]
        failures = 0
        try:
            while pos[i] <= end and not abort.is_set():
                while control.paused and not abort.is_set():
                    time.sleep(0.3)
                control.check()
                before = pos[i]
                try:
                    h = dict(headers or {})
                    h["Range"] = f"bytes={pos[i]}-{end}"
                    with requests.get(url, headers=h, stream=True, timeout=(15, 60)) as r:
                        if r.status_code != 206:
                            raise OSError(f"the server stopped accepting ranges ({r.status_code})")
                        with open(path, "r+b") as f:
                            f.seek(pos[i])
                            for chunk in r.iter_content(CHUNK):
                                if not chunk:
                                    continue
                                if control.paused or control.cancelled or abort.is_set():
                                    break          # reconnect after the pause from where we are
                                take = min(len(chunk), end - pos[i] + 1)
                                f.write(chunk[:take])
                                with lock:
                                    pos[i] += take
                                if pos[i] > end:
                                    break
                except Cancelled:
                    raise
                except Exception:
                    if control.cancelled:
                        raise Cancelled()
                    failures = 0 if pos[i] > before else failures + 1
                    if failures >= RETRIES:
                        raise
                    time.sleep(min(2 * failures, 8))
            control.check()
        except BaseException as e:      # noqa: BLE001 - handed to the main thread
            errors.append(e)
            abort.set()

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(len(parts))]
    for t in threads:
        t.start()
    while any(t.is_alive() for t in threads):
        time.sleep(0.3)
        if on_progress:
            on_progress(_done(parts, pos), total)
    if errors:
        cancelled = [e for e in errors if isinstance(e, Cancelled)]
        raise (cancelled or errors)[0]
    done = _done(parts, pos)
    if done != total:
        raise OSError(f"only {done} of {total} bytes arrived")
    if on_progress:
        on_progress(total, total)


def _done(parts, pos):
    return sum(min(pos[i], parts[i][1] + 1) - parts[i][0] for i in range(len(parts)))


def _single(url, path, headers, total, control, on_progress):
    """One stream: the server has no ranges (or no size)."""
    last = 0.0
    with requests.get(url, headers=headers, stream=True, timeout=(15, 60)) as r:
        r.raise_for_status()
        total = total or int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(path, "wb") as f:
            for chunk in r.iter_content(CHUNK):
                control.wait_while_paused()
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                now = time.monotonic()
                if on_progress and now - last >= 0.4:
                    last = now
                    on_progress(done, total)
        if on_progress:
            on_progress(done, total or done)
