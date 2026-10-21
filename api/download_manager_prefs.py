"""Download manager settings (Settings > Downloads and storage): how many pieces one
file is cut into, how many files download at the same time, and whether the empty
file of the final size is created before the download starts."""
from api.github.auth import _settings_store

_KEY = "download_manager"
SEGMENT_CHOICES = (1, 2, 4, 8, 16)
PARALLEL_CHOICES = (1, 2, 3, 4)
_DEFAULTS = {"segments": 4, "parallel": 2, "preallocate": True}


def _load() -> dict:
    out = dict(_DEFAULTS)
    try:
        if _settings_store.exists(_KEY):
            out.update(dict(_settings_store.get(_KEY)))
    except Exception:
        pass
    return out


def _save(**changes) -> None:
    data = _load()
    data.update(changes)
    _settings_store.put(_KEY, **data)


def segments() -> int:
    v = _load().get("segments")
    return v if v in SEGMENT_CHOICES else _DEFAULTS["segments"]


def parallel() -> int:
    v = _load().get("parallel")
    return v if v in PARALLEL_CHOICES else _DEFAULTS["parallel"]


def preallocate() -> bool:
    return bool(_load().get("preallocate", True))


def _next(choices, current):
    return choices[(choices.index(current) + 1) % len(choices)] if current in choices else choices[0]


def cycle_segments() -> int:
    v = _next(SEGMENT_CHOICES, segments())
    _save(segments=v)
    return v


def cycle_parallel() -> int:
    v = _next(PARALLEL_CHOICES, parallel())
    _save(parallel=v)
    return v


def toggle_preallocate() -> bool:
    v = not preallocate()
    _save(preallocate=v)
    return v
