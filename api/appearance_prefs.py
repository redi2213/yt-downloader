"""Appearance choices kept on this phone: language, theme, own colors, font,
text size and box size. Nothing here knows about Kivy - core/appearance.py
turns these values into colors and sizes.
"""
from api.github.auth import _settings_store

_KEY = "appearance"
DEFAULTS = {"lang": "en", "theme": "classic", "colors": {}, "font": "", "font_scale": 1.0, "box_scale": 1.0,
            "date_mode": "gregorian"}


def load() -> dict:
    out = dict(DEFAULTS)
    out["colors"] = {}
    try:
        if _settings_store.exists(_KEY):
            saved = dict(_settings_store.get(_KEY))
            for key in DEFAULTS:
                if key in saved:
                    out[key] = saved[key]
            out["colors"] = dict(out["colors"] or {})
    except Exception:
        pass
    return out


def save(**changes) -> dict:
    data = load()
    data.update(changes)
    _settings_store.put(_KEY, **data)
    return data
