"""In-app browser choices kept on this phone: how the found files are sorted (also the default next time),
which file types it looks for and the custom extensions (they stay after the app is closed)."""
from api.github.auth import _settings_store

_KEY = "browser"


def _load() -> dict:
    try:
        if _settings_store.exists(_KEY):
            return dict(_settings_store.get(_KEY))
    except Exception:
        pass
    return {}


def get_sort() -> str:
    """The saved sort mode, or "" when none was chosen yet (core/browser_media.SORT_MODES checks it)."""
    return str(_load().get("sort") or "")


def set_sort(value) -> None:
    data = _load()
    data["sort"] = str(value or "")
    _settings_store.put(_KEY, **data)


def get_types() -> str:
    """The switched-on file types as "video,audio,..."; "none" when all are off; "" when never chosen (all on)."""
    return str(_load().get("types") or "")


def set_types(value) -> None:
    data = _load()
    data["types"] = str(value or "")
    _settings_store.put(_KEY, **data)


def get_custom() -> str:
    """The custom extensions typed by hand, without dots: "torrent,iso"."""
    return str(_load().get("custom") or "")


def set_custom(value) -> None:
    data = _load()
    data["custom"] = str(value or "")
    _settings_store.put(_KEY, **data)


def get_data(name):
    """A saved list or dict of the browser (\"tabs\", \"history\", \"bookmarks\"), or None when nothing was saved."""
    try:
        key = "browser_" + name
        if _settings_store.exists(key):
            return _settings_store.get(key).get("data")
    except Exception:
        pass
    return None


def set_data(name, value) -> None:
    _settings_store.put("browser_" + name, data=value)


def get_flag(name) -> bool:
    """A saved on/off choice of the page tools ("dark", "no_images", "no_videos"); off when never chosen."""
    return bool(_load().get("flag_" + str(name)))


def set_flag(name, on) -> None:
    data = _load()
    data["flag_" + str(name)] = bool(on)
    _settings_store.put(_KEY, **data)
