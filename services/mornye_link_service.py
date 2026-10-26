"""Gets Mornye (Tidal lossless) links from the phone itself (see api/mornye.py).

Like filimo_link_service there is no GitHub workflow here: nothing is
dispatched and nothing is polled. The one thing that needs the person is the
one-time browser check: the worker thread asks the UI to show it, then waits
until the person pastes the code (submit_grant) or cancels.
"""
import queue
import threading

from api import mornye
from core.async_utils import run_in_background

WAIT_SECONDS = 280          # the gateway's challenge lives 5 minutes

_grants = queue.Queue()
_cancelled = threading.Event()


def cancel() -> None:
    """Stops the running fetch (also frees a thread waiting for the code)."""
    _cancelled.set()
    _grants.put(None)


def submit_grant(text: str) -> bool:
    """The text the person pasted from the verification page. False if it does
    not look like a code (nothing is passed on then)."""
    if not mornye.parse_grant(text):
        return False
    _grants.put(text)
    return True


def start_fetch_links(url: str, quality: str, progress, show_verify, on_done) -> None:
    """progress(text) and show_verify(challenge_url) and on_done(result) are all
    called from a background thread. on_done gets either {'ok': True, 'title',
    'links', 'names', 'named_links', 'info', 'failed'} or {'ok': False, 'error'}."""
    _cancelled.clear()
    while not _grants.empty():
        try:
            _grants.get_nowait()
        except queue.Empty:
            break
    run_in_background(_thread, url, quality, progress, show_verify, on_done)


def _thread(url, quality, progress, show_verify, on_done):
    def ask(challenge_url):
        show_verify(challenge_url)
        try:
            item = _grants.get(timeout=WAIT_SECONDS)
        except queue.Empty:
            raise mornye.MornyeError("The browser check was not finished in time")
        if item is None:
            raise mornye.Cancelled("Cancelled")
        return item

    try:
        res = mornye.fetch_links(url, quality, progress, ask, _cancelled.is_set)
        on_done({"ok": True, **res, "log": mornye.get_log()})
    except mornye.MornyeError as e:
        on_done({"ok": False, "error": str(e), "log": mornye.get_log()})
    except Exception as e:
        mornye._log(f"unexpected {type(e).__name__}: {str(e)[:200]}")
        on_done({"ok": False, "error": f"Error: {str(e)[:80]}", "log": mornye.get_log()})
