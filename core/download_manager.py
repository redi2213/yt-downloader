"""The download manager: every "Download in app" file goes through ``run()``.

``run()`` is called from a background thread (by core/android_downloads.download_to_downloads),
waits for a free slot (Settings: how many files at the same time), downloads the file in pieces
(core/segmented_download.py) and saves it in the save folder. While it works the file is a
``Task`` that the Downloads page lists and controls (Pause / Resume / Stop). A finished file is
written to api/downloads_history.py.

A file can also be only *added* (state ADDED: it waits in the Adding tab until the user starts it) or
*scheduled* (state SCHEDULED: the scheduler starts it inside the daily time window, by the phone's
clock - api/download_queue_prefs.py, core/download_schedule.py). Waiting files are saved, so they stay
after the app is closed. No Kivy in here.
"""
import os
import tempfile
import threading
import time
from collections import OrderedDict

from api import download_manager_prefs, downloads_history
from core import segmented_download as sd

QUEUED, RUNNING, PAUSED, SAVING, DONE, FAILED, CANCELLED, ADDED, SCHEDULED = (
    "queued", "running", "paused", "saving", "done", "failed", "cancelled", "added", "scheduled")
KEEP_FINISHED = 15            # finished / failed tasks kept in the live list

_tasks = OrderedDict()        # id -> Task
_cond = threading.Condition()
_running = 0                  # tasks that hold a slot
_counter = 0
_sched = {"thread": None, "restored": False, "inside": None, "hold": False}
SCHEDULER_EVERY = 15          # seconds between two looks at the clock


class Task:
    def __init__(self, task_id, name, category, url=None, headers=None, hls=None):
        self.id = task_id
        self.url = url                 # kept for files that wait (ADDED / SCHEDULED)
        self.headers = headers
        self.hls = hls
        self.scheduled = False         # belongs to the Scheduler tab
        self.by_schedule = False       # started by the scheduler (the stop time pauses it)
        self.sched_paused = False      # paused by the stop time, resumes at the next start time
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
        return self.state in (QUEUED, RUNNING, PAUSED, SAVING, ADDED, SCHEDULED)

    @property
    def pending(self):
        """Added or scheduled, not started yet."""
        return self.state in (ADDED, SCHEDULED)


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


def run(url, name, on_progress=None, headers=None, category="Other", hls=None, task=None):
    """Downloads ``url`` and saves it; returns what ``android_downloads._save_in_downloads`` returns.
    A .m3u8 link (or ``hls=True``) is an HLS stream: all its segments are joined into one video file
    (core/hls_download.py). Raises ``segmented_download.Cancelled`` when the user stops it.
    ``task``: an added / scheduled file that starts now (its Task is used instead of a new one)."""
    from core import android_downloads, hls_download
    name = name or android_downloads.file_name_from_url(url)
    is_hls = hls_download.looks_like_hls(url) if hls is None else bool(hls)
    if task is None:
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
    if task.pending:
        remove_pending([task_id])
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


# -- files that only wait: Adding tab and Scheduler tab ---------------------------------------------
def add_pending(url, name=None, headers=None, category="Other", hls=None, scheduled=False):
    """Puts a file in the list WITHOUT starting it (tab Adding), or in the Scheduler tab when
    ``scheduled``. The same link twice gives the same Task. Returns the Task."""
    global _counter
    from core import android_downloads
    name = name or android_downloads.file_name_from_url(url)
    with _cond:
        task = next((t for t in _tasks.values() if t.pending and t.url == url), None)
        if task is None:
            _counter += 1
            task = Task(_counter, name, category, url=url, headers=headers or None, hls=hls)
            task.state = ADDED
            _tasks[task.id] = task
        if scheduled:
            task.scheduled, task.state = True, SCHEDULED
    _persist()
    ensure_scheduler()
    if scheduled:
        _kick()
    return task


def set_scheduled(task_ids, on=True):
    """Moves waiting files to the Scheduler tab (``on``) or back to the Adding tab. Returns the count."""
    n = 0
    with _cond:
        for tid in task_ids:
            t = _tasks.get(tid)
            if t is not None and t.pending:
                t.scheduled, t.state = bool(on), (SCHEDULED if on else ADDED)
                n += 1
    _persist()
    if on and n:
        ensure_scheduler()
        _kick()
    return n


def remove_pending(task_ids):
    n = 0
    with _cond:
        for tid in task_ids:
            t = _tasks.get(tid)
            if t is not None and t.pending:
                _tasks.pop(tid, None)
                n += 1
        _cond.notify_all()
    _persist()
    return n


def start_task(task_id, by_schedule=False):
    """Starts one waiting file now (it joins the normal queue). Returns True when it started."""
    with _cond:
        t = _tasks.get(task_id)
        if t is None or not t.pending or not t.url:
            return False
        t.by_schedule = bool(by_schedule)
        t.state = QUEUED
    _persist()
    threading.Thread(target=_run_pending, args=(t,), daemon=True).start()
    return True


def _run_pending(task):
    try:
        run(task.url, task.name, headers=task.headers, category=task.category, hls=task.hls, task=task)
    except Exception:
        pass        # Cancelled / failed: the task already shows it (Error tab)


def _persist():
    try:
        from api import download_queue_prefs
        with _cond:
            items = [{"name": t.name, "url": t.url, "headers": dict(t.headers or {}), "category": t.category,
                      "hls": t.hls, "scheduled": t.scheduled}
                     for t in _tasks.values() if t.pending and t.url]
        download_queue_prefs.save_queue(items)
    except Exception:
        pass


def _restore():
    """Loads the waiting files saved by an earlier run of the app. True when the store was readable."""
    global _counter
    try:
        from api import download_queue_prefs
        items = download_queue_prefs.load_queue()
    except Exception:
        return False
    with _cond:
        for it in items:
            url = it.get("url")
            if not url or any(t.url == url and t.pending for t in _tasks.values()):
                continue
            _counter += 1
            t = Task(_counter, it.get("name") or "", it.get("category") or "Other", url=url,
                     headers=it.get("headers") or None, hls=it.get("hls"))
            t.scheduled = bool(it.get("scheduled"))
            t.state = SCHEDULED if t.scheduled else ADDED
            _tasks[t.id] = t
    return True


# -- the scheduler: starts the scheduled files inside the daily window, pauses them at the stop time -
def ensure_scheduler():
    """Restores the saved waiting files (once) and starts the scheduler thread (once). Safe to call often."""
    _ensure_restored()
    with _cond:
        th = _sched["thread"]
        if th is not None and th.is_alive():
            return
        th = threading.Thread(target=_sched_loop, daemon=True)
        _sched["thread"] = th
    th.start()


def _ensure_restored():
    if not _sched["restored"]:
        _sched["restored"] = _restore()


def _sched_loop():
    while True:
        _safe(scheduler_tick)
        time.sleep(SCHEDULER_EVERY)


def _kick():
    threading.Thread(target=lambda: _safe(scheduler_tick), daemon=True).start()


def _safe(fn):
    try:
        fn()
    except Exception:
        pass


def scheduler_tick(now=None):
    from api import download_queue_prefs
    from core import download_schedule as ds
    _ensure_restored()
    cfg = download_queue_prefs.schedule()
    start, stop = ds.parse_hm(cfg["start"]), ds.parse_hm(cfg["stop"])
    inside = bool(cfg["enabled"]) and ds.in_window(start, stop, now)
    was, _sched["inside"] = _sched["inside"], inside
    if inside:
        if not was:                                   # the start time just came
            _sched["hold"] = False
            _resume_scheduled()
        if not _sched["hold"]:
            _start_scheduled()
    elif was and cfg["enabled"] and stop:             # the stop time just came
        _pause_scheduled()


def _start_scheduled():
    for t in snapshot():
        if t.state == SCHEDULED:
            start_task(t.id, by_schedule=True)


def _resume_scheduled():
    for t in snapshot():
        if t.sched_paused and t.state == PAUSED:
            t.sched_paused = False
            resume(t.id)


def _pause_scheduled():
    n = 0
    for t in snapshot():
        if t.by_schedule and t.state == RUNNING:      # a file still waiting for a slot just starts later
            t.sched_paused = True
            pause(t.id)
            n += 1
    return n


def scheduler_start_now():
    """The Start button of the Scheduler tab: every scheduled file starts now."""
    _sched["hold"] = False
    _resume_scheduled()
    _start_scheduled()


def scheduler_stop_now():
    """The Stop button of the Scheduler tab: the files the scheduler started are paused, and nothing
    new starts until the next start time (or the Start button)."""
    _sched["hold"] = True
    return _pause_scheduled()
