"""Which files of a followed channel's release the user has already looked at,
kept on this phone: the rest get the "NEW" mark in the Auto follow menu."""
from api.github.auth import _settings_store

_KEY = "follow_seen"


def _all() -> dict:
    return dict(_settings_store.get(_KEY)) if _settings_store.exists(_KEY) else {}


def get_seen(tag: str) -> set:
    return set(_all().get(tag, []))


def set_seen(tag: str, names) -> None:
    data = _all()
    data[tag] = sorted(set(names))
    _settings_store.put(_KEY, **data)
