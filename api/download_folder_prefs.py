"""Where "Download in app" saves files: the default Download/Yt-bridge, or a folder
the user picked with Android's folder picker (kept as a persistable tree uri)."""
from api.github.auth import _settings_store

_KEY = "download_folder"


def _load() -> dict:
    try:
        if _settings_store.exists(_KEY):
            return dict(_settings_store.get(_KEY))
    except Exception:
        pass
    return {}


def get_tree():
    """(tree uri, label) of the chosen folder, or None for the default."""
    d = _load()
    uri = str(d.get("uri") or "")
    return (uri, str(d.get("label") or uri)) if uri else None


def set_tree(uri, label) -> None:
    d = _load()
    _settings_store.put(_KEY, uri=str(uri), label=str(label), subfolders=bool(d.get("subfolders", True)))


def clear() -> None:
    d = _load()
    _settings_store.put(_KEY, uri="", label="", subfolders=bool(d.get("subfolders", True)))


def subfolders() -> bool:
    return bool(_load().get("subfolders", True))


def set_subfolders(on: bool) -> None:
    d = _load()
    _settings_store.put(_KEY, uri=str(d.get("uri") or ""), label=str(d.get("label") or ""), subfolders=bool(on))
