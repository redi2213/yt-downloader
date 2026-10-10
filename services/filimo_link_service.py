"""Gets a Filimo HLS link from the phone itself (see api/filimo.py).

Deliberately separate from generic_action_service: there is no GitHub
workflow involved, so nothing is dispatched and nothing is polled.
"""
from api import filimo
from core.async_utils import run_in_background


def start_fetch_link(url_or_id: str, quality: str, on_done) -> None:
    """on_done(result) is called from a background thread with either
    {'ok': True, 'title', 'quality', 'link'} or {'ok': False, 'error'}."""
    run_in_background(_thread, url_or_id, quality, on_done)


def _thread(url_or_id, quality, on_done):
    try:
        res = filimo.fetch_link(url_or_id, quality)
        on_done({"ok": True, **res})
    except filimo.FilimoError as e:
        on_done({"ok": False, "error": str(e)})
    except Exception as e:
        on_done({"ok": False, "error": f"Error: {str(e)[:80]}"})
