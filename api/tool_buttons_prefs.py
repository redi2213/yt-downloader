"""Buttons found on the first screen of each Lab tool, remembered on this phone so that
Settings > App tools > Share favorites can list them (plugin id -> button texts).
Filled by screens/plugin_host.py every time a Lab tool is opened."""
from api.github.auth import _settings_store

_KEY = "tool_buttons"


def get_all() -> dict:
    try:
        if _settings_store.exists(_KEY):
            data = dict(_settings_store.get(_KEY)).get("data") or {}
            return {str(k): [str(t) for t in v] for k, v in dict(data).items()}
    except Exception:
        pass
    return {}


def remember(plugin_id, titles) -> None:
    titles = [str(t) for t in titles if t][:40]
    if not titles:
        return
    data = get_all()
    if data.get(plugin_id) != titles:
        data[str(plugin_id)] = titles
        _settings_store.put(_KEY, data=data)
