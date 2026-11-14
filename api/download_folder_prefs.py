"""Where "Download in app" saves files: the default Download/Yt-bridge, or a folder
the user picked with Android's folder picker (kept as a persistable tree uri).

``layout``: "source" = a sub folder per source (APK, YouTube, Aparat ...), "type" = a sub folder per
kind of file (Videos, Audio, APK, Zip, Other), "one" = everything in one folder."""
from api.github.auth import _settings_store

_KEY = "download_folder"
LAYOUTS = ("source", "type", "one")


def _load() -> dict:
    try:
        if _settings_store.exists(_KEY):
            return dict(_settings_store.get(_KEY))
    except Exception:
        pass
    return {}


def _put(d, **changes) -> None:
    data = {"uri": str(d.get("uri") or ""), "label": str(d.get("label") or ""), "layout": layout()}
    data.update(changes)
    data["subfolders"] = data["layout"] != "one"
    _settings_store.put(_KEY, **data)


def get_tree():
    """(tree uri, label) of the chosen folder, or None for the default."""
    d = _load()
    uri = str(d.get("uri") or "")
    return (uri, str(d.get("label") or uri)) if uri else None


def set_tree(uri, label) -> None:
    _put(_load(), uri=str(uri), label=str(label))


def clear() -> None:
    _put(_load(), uri="", label="")


def layout() -> str:
    d = _load()
    value = d.get("layout")
    if value in LAYOUTS:
        return value
    return "source" if d.get("subfolders", True) else "one"


def set_layout(value) -> None:
    _put(_load(), layout=value if value in LAYOUTS else "source")


def cycle_layout() -> str:
    nxt = LAYOUTS[(LAYOUTS.index(layout()) + 1) % len(LAYOUTS)]
    set_layout(nxt)
    return nxt


def subfolders() -> bool:
    return layout() != "one"


def set_subfolders(on: bool) -> None:
    set_layout("source" if on else "one")
