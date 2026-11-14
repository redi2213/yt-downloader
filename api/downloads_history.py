"""The files this app saved on the phone (what the Downloads page lists as finished)."""
import time

from api.github.auth import _settings_store

_KEY = "downloads_history"
MAX_ITEMS = 300


def load() -> list:
    try:
        if _settings_store.exists(_KEY):
            return [dict(x) for x in _settings_store.get(_KEY).get("items", [])]
    except Exception:
        pass
    return []


def _save(items) -> None:
    _settings_store.put(_KEY, items=items[:MAX_ITEMS])


def add(name, location, category, size) -> dict:
    now = time.time()
    entry = {"id": f"{int(now * 1000)}", "name": str(name), "location": str(location or ""),
             "category": str(category or "Other"), "size": int(size or 0),
             "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(now))}
    _save([entry] + load())          # newest first
    return entry


def remove(entry_id) -> None:
    _save([x for x in load() if x.get("id") != entry_id])


def remove_many(entry_ids) -> None:
    """Removes several entries with one read and one write."""
    gone = set(entry_ids)
    _save([x for x in load() if x.get("id") not in gone])


def clear() -> None:
    _save([])
