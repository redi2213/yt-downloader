"""Downloads scheduler settings and the saved Adding / Scheduler list.

* schedule(): {"enabled", "start", "stop"} - times are "HH:MM" by the phone's clock, stop "" = not set.
* load_queue() / save_queue(): the files that wait in the Adding / Scheduler tabs, so they stay after
  the app is closed (core/download_manager.py).
"""
from api.github.auth import _settings_store

_SCHED_KEY = "download_schedule"
_QUEUE_KEY = "download_queue"
_DEFAULTS = {"enabled": False, "start": "02:00", "stop": "06:00"}


def schedule() -> dict:
    out = dict(_DEFAULTS)
    try:
        if _settings_store.exists(_SCHED_KEY):
            out.update(dict(_settings_store.get(_SCHED_KEY)))
    except Exception:
        pass
    out["enabled"] = bool(out.get("enabled"))
    out["start"] = str(out.get("start") or _DEFAULTS["start"])
    out["stop"] = str(out.get("stop") or "")
    return out


def set_schedule(**changes) -> None:
    data = schedule()
    data.update(changes)
    _settings_store.put(_SCHED_KEY, **data)


def load_queue() -> list:
    try:
        if _settings_store.exists(_QUEUE_KEY):
            items = dict(_settings_store.get(_QUEUE_KEY)).get("items")
            return [dict(i) for i in items] if isinstance(items, list) else []
    except Exception:
        pass
    return []


def save_queue(items) -> None:
    _settings_store.put(_QUEUE_KEY, items=list(items))
