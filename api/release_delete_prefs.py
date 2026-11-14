"""After a file was downloaded in app from Release History: ask / always / never delete it from the
release too."""
from api.github.auth import _settings_store

_KEY = "release_delete_mode"
MODES = ("ask", "always", "never")


def mode() -> str:
    try:
        if _settings_store.exists(_KEY):
            value = str(_settings_store.get(_KEY).get("mode") or "ask")
            return value if value in MODES else "ask"
    except Exception:
        pass
    return "ask"


def cycle() -> str:
    nxt = MODES[(MODES.index(mode()) + 1) % len(MODES)]
    _settings_store.put(_KEY, mode=nxt)
    return nxt
