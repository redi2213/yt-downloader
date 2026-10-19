"""Persian help for a failed run: finds the error text in the run's log and
matches it against the patterns of ``config.json`` (branch ``config``, key
``error_help``) - or the copy built into the app (core/error_help.py) when
that file cannot be read. Results of the lookup are kept per run.
"""
import json
import os
import time

from api.github import logs, remote_config as remote_config_api
from core import error_help
from core.async_utils import run_in_background
from core.config import SETTINGS_STORE_FILE
from services import runs_service

_CACHE_FILE = os.path.join(os.path.dirname(SETTINGS_STORE_FILE) or ".", "remote_config_cache.json")
_PATTERN_TTL = 600           # seconds a loaded pattern list is reused
_patterns = {"at": 0.0, "list": None}
_results = {}                # run_id -> help text ("" = nothing matched)


def _from_config(config):
    items = config.get("error_help") if isinstance(config, dict) else None
    return items if isinstance(items, list) and items else None


def load_patterns():
    """Patterns from GitHub, else the copy saved on the phone, else the built-in list."""
    if _patterns["list"] is not None and time.time() - _patterns["at"] < _PATTERN_TTL:
        return _patterns["list"]
    found = None
    for fetch in (remote_config_api.fetch_remote_config, remote_config_api.fetch_remote_config_via_api):
        try:
            found = _from_config(fetch())
        except Exception:
            found = None
        if found:
            break
    if not found:
        try:
            with open(_CACHE_FILE, encoding="utf-8") as f:
                found = _from_config((json.load(f) or {}).get("config"))
        except Exception:
            found = None
    _patterns["list"] = found or error_help.DEFAULT_PATTERNS
    _patterns["at"] = time.time()
    return _patterns["list"]


def start_error_help(run_id, jobs, on_done):
    """``on_done({"ok": True, "text": persian help or ""})`` / ``{"ok": False, "error"}``."""
    def work():
        if run_id in _results:
            return {"text": _results[run_id]}
        job, _step = runs_service.find_failure(jobs)
        if job is None:
            return {"text": ""}
        log = logs.get_job_log_text(job["id"])
        if log is None:
            raise ValueError("The log is not ready yet.")
        text = error_help.help_text(error_help.find_help(runs_service.extract_error(log), load_patterns()))
        _results[run_id] = text
        return {"text": text}
    run_in_background(runs_service._guarded, on_done, work)
