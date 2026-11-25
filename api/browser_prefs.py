"""In-app browser choices kept on this phone: how the found files are sorted (also the default next time),
which file types it looks for and the custom extensions (they stay after the app is closed).

Every browser profile (core/browser_profiles.py) has its own copy of all of this (settings, tabs, history, bookmarks);
the main profile keeps the original keys, so what was saved before profiles existed is still there.
"""
from api.github.auth import _settings_store

_META = "browser_profmeta"         # the list of profiles and which one is active (not per profile)
_DATA_NAMES = ("tabs", "history", "bookmarks", "run_mode")
_active = None


# -- profiles -------------------------------------------------------------------------------------------------------
def get_profiles_data():
    """The saved profile list (see core/browser_profiles.Profiles.to_data), or None when never saved."""
    try:
        if _settings_store.exists(_META):
            data = _settings_store.get(_META).get("data")
            return data if isinstance(data, dict) else None
    except Exception:
        pass
    return None


def set_profiles_data(value) -> None:
    _settings_store.put(_META, data=value)


def active_id() -> str:
    """The active profile id; \"\" is the main profile."""
    global _active
    if _active is None:
        _active = str((get_profiles_data() or {}).get("active") or "")
    return _active


def set_active_id(pid) -> None:
    """Every read and write below goes to this profile from now on (the caller saves the profile list)."""
    global _active
    _active = str(pid or "")


def _key() -> str:
    pid = active_id()
    return "browser_" + pid if pid else "browser"


def _dkey(name) -> str:
    pid = active_id()
    return f"browser_{pid}_{name}" if pid else "browser_" + name


def drop_profile_data(pid) -> None:
    """Forgets everything saved for a deleted profile (never the main one)."""
    pid = str(pid or "")
    if not pid:
        return
    for key in ["browser_" + pid] + [f"browser_{pid}_{n}" for n in _DATA_NAMES]:
        try:
            if hasattr(_settings_store, "delete"):
                _settings_store.delete(key)
            elif _settings_store.exists(key):
                _settings_store.put(key, data=None)
        except Exception:
            pass


# -- the active profile's choices ------------------------------------------------------------------------------------
def _load() -> dict:
    try:
        key = _key()
        if _settings_store.exists(key):
            return dict(_settings_store.get(key))
    except Exception:
        pass
    return {}


def get_sort() -> str:
    """The saved sort mode, or "" when none was chosen yet (core/browser_media.SORT_MODES checks it)."""
    return str(_load().get("sort") or "")


def set_sort(value) -> None:
    data = _load()
    data["sort"] = str(value or "")
    _settings_store.put(_key(), **data)


def get_types() -> str:
    """The switched-on file types as "video,audio,..."; "none" when all are off; "" when never chosen (all on)."""
    return str(_load().get("types") or "")


def set_types(value) -> None:
    data = _load()
    data["types"] = str(value or "")
    _settings_store.put(_key(), **data)


def get_custom() -> str:
    """The custom extensions typed by hand, without dots: "torrent,iso"."""
    return str(_load().get("custom") or "")


def set_custom(value) -> None:
    data = _load()
    data["custom"] = str(value or "")
    _settings_store.put(_key(), **data)


def get_data(name):
    """A saved list or dict of the browser (\"tabs\", \"history\", \"bookmarks\"), or None when nothing was saved."""
    try:
        key = _dkey(name)
        if _settings_store.exists(key):
            return _settings_store.get(key).get("data")
    except Exception:
        pass
    return None


def set_data(name, value) -> None:
    _settings_store.put(_dkey(name), data=value)


def get_flag(name) -> bool:
    """A saved on/off choice of the page tools (\"dark\", \"no_images\", \"no_videos\"); off when never chosen."""
    return bool(_load().get("flag_" + str(name)))


def set_flag(name, on) -> None:
    data = _load()
    data["flag_" + str(name)] = bool(on)
    _settings_store.put(_key(), **data)
