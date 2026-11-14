"""Folders other apps save files in (picked with Android's folder picker). This app only looks into
them to know which files are already on the phone (core/phone_files.py)."""
from api.github.auth import _settings_store

_KEY = "watched_folders"


def load() -> list:
    try:
        if _settings_store.exists(_KEY):
            return [dict(x) for x in _settings_store.get(_KEY).get("items", [])]
    except Exception:
        pass
    return []


def add(uri, label) -> None:
    items = [x for x in load() if x.get("uri") != str(uri)]
    items.append({"uri": str(uri), "label": str(label)})
    _settings_store.put(_KEY, items=items)


def remove(uri) -> None:
    _settings_store.put(_KEY, items=[x for x in load() if x.get("uri") != str(uri)])
