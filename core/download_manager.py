"""The download manager: every "Download in app" file goes through ``run()``.

``run()`` is called from a background thread (by core/android_downloads.download_to_downloads),
waits for a free slot (Settings: how many files at the same time), downloads the file in pieces
(core/segmented_download.py) and saves it in the save folder. While it works the file is a
``Task`` that the Downloads page lists and controls (Pause / Resume / Stop). A finished file is
written to api/downloads_history.py. No Kivy in here.
"""
import os
import tempfile
import threading
import time
from collections import OrderedDict

from api import download_manager_prefs, downloads_history
from core import segmented_download as sd

QUEUED, RUNNING, PAUSED, SAVING, DONE, FAILED, CANCELLED = (
    "queued", "running", "paused", "saving", "done", "failed", "cancelled")
KEEP_FINISHED = 15            # finished / failed tasks kept in the live list

_tasks = OrderedDict()        # id -> Task
_cond = threading.Condition()
_running = 0                  # tasks that hold a slot
_counter = 0


class Task:
    def __init__(self, task_id, name, category):
        self.id = task_id
        self.name = name
        self.category = category
        self.state = QUEUED
        self.done = 0
        self.total = 0
        self.speed = 0.0           # bytes per second
        self.error = ""
        self.saved = None
        self.control = sd.Control()
        self.holds_slot = False
        self._tick = (time.monotonic(), 0)

    def update(self, done, total):
        now = time.monotonic()
        last_t, last_done = self._tick
        if now - last_t >= 0.8:
            self.speed = max(0.0, (done - last_done) / (now - last_t))
            self._tick = (now, done)
        self.done, self.total = done, total or self.total

    @property
    def active(self):
        return self.state in (QUEUED, RUNNING, PAUSED, SAVING)


def snapshot():
    """The live tasks, newest first (a copy, safe to read from the UI thread)."""
    with _cond:
        return list(reversed(_tasks.values()))


def get(task_id):
    with _cond:
        return _tasks.get(task_id)


def _new_task(name, category):
    global _counter
    with _cond:
        _counter += 1
        task = Task(_counter, name, category)
        _tasks[task.id] = task
        return task


def _trim():
    with _cond:
        finished = [t for t in _tasks.values() if not t.active]
        for t in finished[:-KEEP_FINISHED]:
            _tasks.pop(t.id, None)


def _acquire_slot(task):
    global _running
    with _cond:
        while _running >= download_manager_prefs.parallel():
            if task.control.cancelled:
                raise sd.Cancelled()
            task.state = QUEUED
            _cond.wait(0.5)
        task.control.check()
        _running += 1
        task.holds_slot = True
        task.state = RUNNING


def _release_slot(task):
    global _running
    with _cond:
        if task.holds_slot:
            task.holds_slot = False
            _running -= 1
        _cond.notify_all()


def run(url, name, on_progress=None, headers=None, category="Other", hls=None):
    """Downloads ``url`` and saves it; returns what ``android_downloads._save_in_downloads`` returns.
    A .m3u8 link (or ``hls=True``) is an HLS stream: all its segments are joined into one video file
    (core/hls_download.py). Raises ``segmented_download.Cancelled`` when the user stops it."""
    from core import android_downloads, hls_download
    name = name or android_downloads.file_name_from_url(url)
    is_hls = hls_download.looks_like_hls(url) if hls is None else bool(hls)
    task = _new_task(name, category)
    fd, tmp_path = tempfile.mkstemp(suffix=".part")
    os.close(fd)
    try:
        _acquire_slot(task)

        def progress(done, total):
            task.update(done, total)
            if on_progress:
                on_progress(done, total)

        if is_hls:
            ext = hls_download.fetch(url, tmp_path, headers=headers, control=task.control, on_progress=progress)
            name = os.path.splitext(name)[0] + ext          # chunk.m3u8 -> chunk.ts (one playable video)
            task.name = name
        else:
            sd.fetch(url, tmp_path, headers=headers, segments=download_manager_prefs.segments(),
                     preallocate=download_manager_prefs.preallocate(), control=task.control,
                     on_progress=progress)
        task.state = SAVING
        saved = android_downloads._save_in_downloads(tmp_path, name, category)
        task.saved = saved
        task.state = DONE
        try:
            size = os.path.getsize(tmp_path)
        except OSError:
            size = task.total
        downloads_history.add(name, getattr(saved, "location", None), category, size)
        return saved
    except sd.Cancelled:
        task.state = CANCELLED
        raise
    except Exception as e:
        task.state = FAILED
        task.error = str(e)[:80]
        raise
    finally:
        _release_slot(task)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        _trim()


# -- controls used by the Downloads page --------------------------------------------------------
def pause(task_id):
    task = get(task_id)
    if task is None or task.state not in (RUNNING, QUEUED):
        return
    task.control.pause()
    if task.state == RUNNING:
        task.state = PAUSED
        _release_slot(task)          # a paused file does not block the queue


def resume(task_id):
    task = get(task_id)
    if task is None or not task.control.paused:
        return
    task.state = QUEUED
    threading.Thread(target=_resume_when_free, args=(task,), daemon=True).start()


def _resume_when_free(task):
    global _running
    with _cond:
        while _running >= download_manager_prefs.parallel() and not task.control.cancelled:
            _cond.wait(0.5)
        if task.control.cancelled:
            return
        _running += 1
        task.holds_slot = True
        task.state = RUNNING
    task.control.resume()


def cancel(task_id):
    task = get(task_id)
    if task is None or not task.active:
        return
    task.control.cancel()
    with _cond:
        _cond.notify_all()


def forget(task_id):
    """Takes a finished / failed task out of the live list."""
    with _cond:
        t = _tasks.get(task_id)
        if t is not None and not t.active:
            _tasks.pop(task_id, None)


def clear_finished():
    with _cond:
        for tid in [t.id for t in _tasks.values() if not t.active]:
            _tasks.pop(tid, None)
