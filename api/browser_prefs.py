"""In-app browser choices kept on this phone: how the found files are sorted (also the default next time)."""
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
