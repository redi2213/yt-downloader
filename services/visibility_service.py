"""Settings > App tools > Repository visibility: read and flip public/private.

Callbacks may be called from a background thread (see core/async_utils.py).
Each callback gets {"ok": True, "private": bool} or {"ok": False, "error": text}.
"""
from api.github import visibility
from core.async_utils import run_in_background
from core.exceptions import AuthenticationError

ADMIN_HELP = ("The GitHub token cannot change the repo. It needs admin rights "
              "(classic: repo scope as owner; fine-grained: Administration read and write).")


def _guarded(on_done, work):
    try:
        on_done({"ok": True, "private": work()})
    except AuthenticationError:
        on_done({"ok": False, "error": ADMIN_HELP})
    except Exception as e:
        on_done({"ok": False, "error": f"Error: {str(e)[:80]}"})


def start_load(on_done):
    run_in_background(_guarded, on_done, visibility.is_private)


def start_set_private(private, on_done):
    run_in_background(_guarded, on_done, lambda: visibility.set_private(private))
