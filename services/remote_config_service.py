"""Fetching the remotely-hosted action/button list so new features (e.g. a
new download source) can appear in the app without a rebuild.

Same shape as the rest of services/: fire-and-forget from the caller's
perspective, background thread, result delivered via on_complete.
"""
from api.github import remote_config as remote_config_api
from core.async_utils import run_in_background

# Shipped inside the APK as a safety net - used if the device has no
# network, or the remote config fetch fails/returns malformed data, so the
# app is never left with zero buttons.
_FALLBACK_CONFIG = {
    "config_version": 0,
    "actions": [
        {
            "id": "youtube_download",
            "title": "دانلود از یوتیوب",
            "icon": "youtube",
            "enabled": True,
            "input_type": "url",
            "input_hint": "لینک ویدیو یوتیوب را وارد کنید",
            "workflow": "download-anything.yml",
            "workflow_inputs": {
                "video_url": "{input}",
                "output_mode": "upload_release",
            },
        },
    ],
}


def start_load_actions(on_complete=None):
    """on_complete receives a dict: {"ok": bool, "actions": list, "source": "remote"|"fallback"}"""
    run_in_background(_load_actions_thread, on_complete)


def _load_actions_thread(on_complete):
    try:
        config = remote_config_api.fetch_remote_config()
        actions = _extract_enabled_actions(config)
        _emit_complete(on_complete, {"ok": True, "actions": actions, "source": "remote"})
    except Exception:
        actions = _extract_enabled_actions(_FALLBACK_CONFIG)
        _emit_complete(on_complete, {"ok": True, "actions": actions, "source": "fallback"})


def _extract_enabled_actions(config: dict) -> list:
    actions = config.get("actions", [])
    return [a for a in actions if a.get("enabled", True)]


def _emit_complete(on_complete, payload):
    if on_complete:
        on_complete(payload)
