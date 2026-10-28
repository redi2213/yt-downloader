"""The v2ray config of the Any site workflow, kept as the GitHub secret V2RAY_CONFIG.

Saved from Settings > Downloads and storage > Proxy / v2ray config. The workflow uses it when the
"v2ray config" box of Any site is empty, so one saved config works for every run; the box overrides it
for one run. A secret cannot be read back (only its name can be listed), so the screen only shows
"saved" or "not saved". Blocking functions run in a background thread; no Kivy here.
"""
import json
import re

from api.github import secrets
from core.async_utils import run_in_background
from core.exceptions import AuthenticationError

SECRET_NAME = "V2RAY_CONFIG"
MAX_LEN = 48000
_TOKEN_RE = re.compile(r"^(vless|vmess|trojan|ss|https?)://", re.IGNORECASE)


def normalize(text):
    """(value, error). The value is one line: links separated by single spaces, or a minified JSON.
    One line matters: GitHub hides every line of a secret in the logs, and short lines like "}" would
    wipe parts of the log."""
    raw = (text or "").strip()
    if not raw:
        return "", "Paste a config first."
    if raw[:1] in "{[":
        try:
            value = json.dumps(json.loads(raw), separators=(",", ":"), ensure_ascii=False)
        except ValueError:
            return "", "This JSON is not valid."
    else:
        tokens = [t for t in re.split(r"\s+", raw) if _TOKEN_RE.match(t)]
        if not tokens:
            return "", "No vless:// vmess:// trojan:// ss:// link or subscription link was found."
        value = " ".join(tokens)
    if len(value) > MAX_LEN:
        return "", "This config is too long for a GitHub secret."
    return value, ""


def _error_text(e):
    if isinstance(e, AuthenticationError):
        return "GitHub token invalid or expired. Update it and retry."
    return f"Error: {str(e)[:80]}"


def start_status(on_complete):
    """on_complete({'ok': True, 'saved': bool}) or {'ok': False, 'error': str}."""
    run_in_background(_status_thread, on_complete)


def _status_thread(on_complete):
    try:
        on_complete({"ok": True, "saved": SECRET_NAME in secrets.list_secret_names()})
    except Exception as e:
        on_complete({"ok": False, "error": _error_text(e)})


def start_save(value, on_complete):
    run_in_background(_save_thread, value, on_complete)


def _save_thread(value, on_complete):
    try:
        secrets.put_secret(SECRET_NAME, value)
        on_complete({"ok": True})
    except Exception as e:
        on_complete({"ok": False, "error": _error_text(e)})


def start_delete(on_complete):
    run_in_background(_delete_thread, on_complete)


def _delete_thread(on_complete):
    try:
        secrets.delete_secret(SECRET_NAME)
        on_complete({"ok": True})
    except Exception as e:
        on_complete({"ok": False, "error": _error_text(e)})
