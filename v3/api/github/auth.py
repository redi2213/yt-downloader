"""GitHub token storage and request headers.

Uses Kivy's JsonStore for on-device persistence, but nothing else in the
``api`` or ``core`` layers depends on Kivy - this is the one deliberate,
contained exception because Kivy ships a convenient cross-platform
key/value store.
"""
from kivy.storage.jsonstore import JsonStore

from core.config import SETTINGS_STORE_FILE

_settings_store = JsonStore(SETTINGS_STORE_FILE)


def get_token() -> str:
    if _settings_store.exists("github"):
        return _settings_store.get("github")["token"]
    return ""


def save_token(token: str) -> None:
    _settings_store.put("github", token=token)


def auth_headers() -> dict:
    return {"Authorization": f"token {get_token()}", "Accept": "application/vnd.github+json"}
