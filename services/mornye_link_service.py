"""Downloads Mornye (lossless) music on the phone itself (see api/mornye.py).

Like filimo_link_service there is no GitHub workflow here: nothing is dispatched
and nothing is polled - api.zarz.moe blocks GitHub's IPs, so the phone's own
network does everything. The only thing that needs the person is the one-time
browser check: the worker thread asks the UI to show it, then waits until the
person pastes the code (submit_grant) or cancels.

After every run the step log (no secrets) is also saved to the repo's config
branch under logs/, so a failure can be read without copying anything.
"""
import queue
import shutil
import tempfile
import threading
import time

from api import mornye
from core import android_downloads, mornye_download
from core.async_utils import run_in_background

WAIT_SECONDS = 280          # the gateway's challenge lives 5 minutes
CATEGORY = "Mornye"

_grants = queue.Queue()
_cancelled = threading.Event()


def cancel() -> None:
    """Stops the running download (also frees a thread waiting for the code)."""
    _cancelled.set()
    _grants.put(None)


def submit_grant(text: str) -> bool:
    """The text the person pasted from the verification page. False if it does
    not look like a code (nothing is passed on then)."""
    if not mornye.parse_grant(text):
        return False
    _grants.put(text)
    return True


def start_download(url: str, quality: str, providers: str, progress, show_verify,
                   on_done) -> None:
    """progress(text), show_verify(challenge_url) and on_done(result) are all
    called from a background thread. on_done gets {'ok': True, 'title', 'saved',
    'failed', 'folder', 'log', 'log_path'} or {'ok': False, 'error', 'log',
    'log_path'}."""
    _cancelled.clear()
    while not _grants.empty():
        try:
            _grants.get_nowait()
        except queue.Empty:
            break
    run_in_background(_thread, url, quality, providers, progress, show_verify, on_done)


def _upload_log(text: str) -> str:
    """Saves the log on the config branch; '' when that did not work."""
    try:
        from api.github import repo_files
        path = "logs/mornye-%s.txt" % time.strftime("%Y%m%d-%H%M%S")
        repo_files.replace_file("config", path, text.encode("utf-8"), "log: " + path)
        return path
    except Exception:
        return ""


def _thread(url, quality, providers, progress, show_verify, on_done):
    def ask(challenge_url):
        show_verify(challenge_url)
        try:
            item = _grants.get(timeout=WAIT_SECONDS)
        except queue.Empty:
            raise mornye.MornyeError("The browser check was not finished in time")
        if item is None:
            raise mornye.Cancelled("Cancelled")
        return item

    def handle(pos, total, track, item, numbered):
        label = " - ".join(p for p in (track["artist"], track["title"]) if p) or "track"
        work = tempfile.mkdtemp(prefix="mornye_")
        try:
            def status(text):
                progress("%d/%d %s - %s" % (pos, total, label[:40], text))
            try:
                path, ext = mornye_download.fetch(item, work, status, _cancelled.is_set)
            except mornye_download.DownloadCancelled:
                raise mornye.Cancelled("Cancelled")
            name = mornye.file_name(pos, total, track, ext, numbered)
            android_downloads._save_in_downloads(path, name, CATEGORY)
            mornye._log("saved %s (%s, %s)" % (name, item.get("provider"), item.get("kind")))
            return name
        finally:
            shutil.rmtree(work, ignore_errors=True)

    order = [p.strip() for p in str(providers or "").split(",") if p.strip()]
    result = {}
    try:
        res = mornye.run_tracks(url, quality, order, progress, ask, _cancelled.is_set, handle)
        result = {"ok": True, **res, "folder": android_downloads.folder_label(CATEGORY)}
    except mornye.MornyeError as e:
        result = {"ok": False, "error": str(e)}
    except Exception as e:
        mornye._log("unexpected %s: %s" % (type(e).__name__, str(e)[:200]))
        result = {"ok": False, "error": "Error: %s" % str(e)[:80]}
    kind, sid = mornye.parse_spotify(url)
    header = "Mornye log %s | %s %s | providers %s | %s\n" % (
        time.strftime("%Y-%m-%d %H:%M:%S"), kind or "?", sid or "?", providers,
        "OK" if result.get("ok") else "FAILED: " + str(result.get("error")))
    result["log"] = header + mornye.get_log()
    result["log_path"] = _upload_log(result["log"])
    on_done(result)
