"""Remembers which Release History files were downloaded in app (name + size -> the release item), so
the app can offer to delete them from the release afterwards (screens/downloads.py)."""
from api import release_delete_prefs
from api.github.auth import _settings_store
from core import phone_files

_KEY = "release_links"
MAX = 200


def _load() -> dict:
    try:
        if _settings_store.exists(_KEY):
            return dict(_settings_store.get(_KEY).get("records", {}))
    except Exception:
        pass
    return {}


def _save(records) -> None:
    keys = list(records)[-MAX:]
    _settings_store.put(_KEY, records={k: records[k] for k in keys})


def _clean(item):
    return {k: v for k, v in dict(item).items() if isinstance(v, (str, int, float, bool)) or v is None}


def key_of_item(item):
    return phone_files.key(item.get("title"), item.get("size"))


def remember(items) -> None:
    """Only the files of the app's own GitHub releases (they can be deleted from there)."""
    records = _load()
    for item in items:
        if item.get("asset_id") is None or item.get("repo") or not item.get("title"):
            continue
        k = key_of_item(item)
        records.pop(k, None)
        records[k] = {"key": k, "asked": False, "item": _clean(item)}
    _save(records)


def get(name, size):
    """The record of a downloaded file (``{"key", "asked", "item"}``), or None."""
    return _load().get(phone_files.key(name, size))


def mark_asked(keys) -> None:
    records = _load()
    for k in keys:
        if k in records:
            records[k]["asked"] = True
    _save(records)


def forget_item(item) -> None:
    records = _load()
    if records.pop(key_of_item(item), None) is not None:
        _save(records)


def mode() -> str:
    return release_delete_prefs.mode()
