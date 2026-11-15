"""The exported cookies kept as a GitHub secret the workflows read (cookies.txt in Netscape format).

YTDLP_COOKIES is read by the YouTube workflows (download, list formats / playlist, Auto-Follow) and COOKIES_TXT by
Any site (names and labels as in services/health_service.py). Saving replaces the secret: a secret cannot be read
back (only its name can be listed), so the old cookies cannot be merged. The value is encrypted by
api/github/secrets.py before it leaves the phone. Cookie values never go into an error text (``redact``).
Blocking functions run in a background thread; no Kivy here.
"""
from api.github import secrets
from core import browser_cookies as bc
from core.async_utils import run_in_background
from core.exceptions import AuthenticationError

TARGETS = (
    ("YTDLP_COOKIES", "YouTube downloads (cookies, avoids the bot check)"),
    ("COOKIES_TXT", "Any site (cookies, optional)"),
)
NAMES = tuple(name for name, _label in TARGETS)


def _error_text(e, value=""):
    if isinstance(e, AuthenticationError):
        return "GitHub token invalid or expired. Update it and retry."
    return "Error: " + bc.redact(str(e), value)[:80]


def start_status(on_complete):
    """on_complete({'ok': True, 'saved': [names of the cookie secrets that exist]}) or {'ok': False, 'error': str}."""
    run_in_background(_status_thread, on_complete)


def _status_thread(on_complete):
    try:
        have = set(secrets.list_secret_names())
        on_complete({"ok": True, "saved": [n for n in NAMES if n in have]})
    except Exception as e:
        on_complete({"ok": False, "error": _error_text(e)})


def start_save(name, cookies_txt, on_complete):
    """Replaces the secret ``name`` with ``cookies_txt``. on_complete({'ok': True}) or {'ok': False, 'error': str}."""
    run_in_background(_save_thread, name, cookies_txt, on_complete)


def _save_thread(name, cookies_txt, on_complete):
    value, problem = bc.valid_cookies_txt(cookies_txt)
    if name not in NAMES or problem:
        on_complete({"ok": False, "error": problem or "Could not send"})
        return
    try:
        secrets.put_secret(name, value)
        on_complete({"ok": True})
    except Exception as e:
        on_complete({"ok": False, "error": _error_text(e, value)})
