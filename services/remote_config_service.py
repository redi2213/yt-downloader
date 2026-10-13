"""Fetching the remotely-hosted action/button list so new features (e.g. a
new download source) can appear in the app without a rebuild.

Same shape as the rest of services/: fire-and-forget from the caller's
perspective, background thread, result delivered via on_complete.

Where the list comes from, in order:
  1. GitHub, read two ways (raw.githubusercontent.com, or the signed-in
     GitHub API); the way that worked last time is tried first
  2. the copy saved on this phone after the last successful load
  3. the one built-in button (last resort)
When it is not (1) the result carries a ``notice`` explaining why, so the
screen can say so instead of silently showing a short list.
"""
import json
import os

from api.github import remote_config as remote_config_api
from core.async_utils import run_in_background
from core.config import SETTINGS_STORE_FILE

# Shipped inside the APK as a safety net - used if the device has no
# network and nothing was ever saved, so the app is never left with zero buttons.
_FALLBACK_CONFIG = {
    "config_version": 0,
    "actions": [
        {
            "id": "any_site_upload",
            "title": "Any site (extract & upload)",
            "icon": "download",
            "enabled": True,
            "input_type": "url",
            "input_hint": "Enter the video link",
            "workflow": "Any-Site-Upload.yml",
            "workflow_inputs": {
                "mode": "release",
                "urls": "{input}",
                "quality": "720",
            },
        },
    ],
}

_FETCHERS = {
    "raw": remote_config_api.fetch_remote_config,
    "api": remote_config_api.fetch_remote_config_via_api,
}
_CACHE_FILE = os.path.join(os.path.dirname(SETTINGS_STORE_FILE) or ".", "remote_config_cache.json")


def start_load_actions(on_complete=None):
    """on_complete receives a dict: {"ok": True, "actions": list,
    "source": "remote" | "cached" | "fallback", "notice": str}"""
    run_in_background(_load_actions_thread, on_complete)


def _read_cache() -> dict:
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_cache(config: dict, via: str) -> None:
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"via": via, "config": config}, f)
    except Exception:
        pass  # a missing saved copy is not worth failing the screen for


def _check(config) -> dict:
    if not isinstance(config, dict) or not isinstance(config.get("actions"), list):
        raise ValueError("config.json has no actions list")
    return config


def _load_actions_thread(on_complete):
    cache = _read_cache()
    order = list(_FETCHERS)
    if cache.get("via") in order:  # the way that worked last time goes first
        order.remove(cache["via"])
        order.insert(0, cache["via"])

    problems = []
    for via in order:
        try:
            config = _check(_FETCHERS[via]())
        except Exception as e:
            problems.append(f"{via}: {str(e)[:70]}")
            continue
        _write_cache(config, via)
        _emit_complete(on_complete, {
            "ok": True, "source": "remote", "notice": "",
            "actions": _extract_enabled_actions(config),
        })
        return

    reason = "; ".join(problems)
    saved = cache.get("config")
    if isinstance(saved, dict) and isinstance(saved.get("actions"), list):
        _emit_complete(on_complete, {
            "ok": True, "source": "cached", "actions": _extract_enabled_actions(saved),
            "notice": f"Could not reach GitHub - showing the list saved on this phone.\n({reason})",
        })
        return
    _emit_complete(on_complete, {
        "ok": True, "source": "fallback", "actions": _extract_enabled_actions(_FALLBACK_CONFIG),
        "notice": f"Could not load the full list - only the built-in button is shown.\n({reason})",
    })


def _extract_enabled_actions(config: dict) -> list:
    actions = config.get("actions", [])
    return [a for a in actions if a.get("enabled", True)]


def _emit_complete(on_complete, payload):
    if on_complete:
        on_complete(payload)
