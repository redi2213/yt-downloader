"""Favorite tools of the share list (Settings > App tools > Share favorites), kept on this phone.

Ids: builtin:youtube | builtin:upload | builtin:browser | action:<id> | lab:<plugin> | lab:<plugin>:<quick>
(<quick> = one button inside a Lab tool, listed under "quick" in lab/index.json).
"""
from api.github.auth import _settings_store

_KEY = "share_favs"


def get_ids() -> list:
    try:
        if _settings_store.exists(_KEY):
            return [str(x) for x in list(dict(_settings_store.get(_KEY)).get("ids") or []) if x]
    except Exception:
        pass
    return []


def set_ids(ids) -> None:
    out = []
    for i in ids:
        if i and i not in out:
            out.append(i)
    _settings_store.put(_KEY, ids=out)


def toggle(item_id) -> bool:
    """Add or remove; True when it is a favorite now."""
    ids = get_ids()
    if item_id in ids:
        ids.remove(item_id)
    else:
        ids.append(item_id)
    set_ids(ids)
    return item_id in ids


def move(item_id, delta) -> None:
    ids = get_ids()
    if item_id not in ids:
        return
    a = ids.index(item_id)
    b = max(0, min(len(ids) - 1, a + delta))
    ids.insert(b, ids.pop(a))
    set_ids(ids)
