# LAB COPY of api/mornye_prefs.py: edit freely, the app's own file is untouched.
"""Mornye settings kept on the phone: download order, fallback ticks, registry URL.

The app itself implements only Tidal, Qobuz and Deezer (api/mornye.py), so only
those can be ordered / ticked; the others are listed as "coming soon".
"""
import json

import requests

from api.github.auth import _settings_store

KEY = "mornye_lab_prefs"          # own settings: the app's Mornye keeps "mornye_prefs"
ORIGINAL_KEY = "mornye_prefs"
SUPPORTED = ["tidal", "qobuz", "deezer"]
NAMES = {"tidal": "Tidal", "qobuz": "Qobuz", "deezer": "Deezer"}
SOON = ["Amazon Music", "YouTube Music", "SoundCloud", "JioSaavn"]
DEFAULT_REGISTRY = ("https://raw.githubusercontent.com/mornyeapp/Mornye-Extension/"
                    "main/registry.json")


def load() -> dict:
    """{'order': [...], 'enabled': [...], 'registry': str} - always complete."""
    rec = {}
    try:
        if _settings_store.exists(KEY):
            rec = dict(_settings_store.get(KEY))
        elif _settings_store.exists(ORIGINAL_KEY):   # first use: start from the app's settings
            rec = dict(_settings_store.get(ORIGINAL_KEY))
    except Exception:
        rec = {}
    order = [p for p in (rec.get("order") or []) if p in SUPPORTED]
    order += [p for p in SUPPORTED if p not in order]
    enabled = rec.get("enabled")
    enabled = [p for p in SUPPORTED if p in enabled] if isinstance(enabled, list) else list(SUPPORTED)
    return {"order": order, "enabled": enabled,
            "registry": str(rec.get("registry") or "").strip()}


def save(order, enabled, registry) -> None:
    _settings_store.put(KEY, order=list(order), enabled=list(enabled),
                        registry=str(registry or "").strip())


def providers_string() -> str:
    """The ordered, ticked providers as 'tidal,qobuz' (never empty)."""
    prefs = load()
    chosen = [p for p in prefs["order"] if p in prefs["enabled"]]
    return ",".join(chosen or prefs["order"])


def check_registry(url: str) -> list:
    """Reads a registry.json -> ['tidal-web 1.2.5', ...]; raises ValueError with a short text."""
    url = (url or "").strip() or DEFAULT_REGISTRY
    if not url.startswith("http"):
        raise ValueError("The repo link must start with https://")
    try:
        resp = requests.get(url, timeout=25, headers={"User-Agent": "YT-Bridge"})
    except requests.exceptions.RequestException as e:
        raise ValueError("Network error: " + str(e)[:80])
    if resp.status_code != 200:
        raise ValueError("HTTP %d from the repo link" % resp.status_code)
    try:
        data = json.loads(resp.text)
    except ValueError:
        raise ValueError("That link is not a registry.json file")
    items = data.get("extensions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("No extensions list in this registry")
    return ["%s %s" % (i.get("id", "?"), i.get("version", "")) for i in items
            if isinstance(i, dict)]
