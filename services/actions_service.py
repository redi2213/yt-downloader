"""Listing recent GitHub Actions runs and inspecting one run's steps -
independent of any job the app itself started."""
from api.github import workflows
from core.async_utils import run_in_background
from core.exceptions import AuthenticationError

_TOKEN_ERROR = "GitHub token invalid or expired. Update it and retry."


def start_load_recent_runs(on_complete=None):
    run_in_background(_load_recent_runs_thread, on_complete)


def _load_recent_runs_thread(on_complete):
    try:
        runs = workflows.get_recent_runs()
        _emit_complete(on_complete, {"ok": True, "runs": runs})
    except AuthenticationError:
        _emit_complete(on_complete, {"ok": False, "error": _TOKEN_ERROR})
    except Exception as e:
        _emit_complete(on_complete, {"ok": False, "error": f"Could not fetch status: {str(e)[:60]}"})


def start_load_run_steps(run_id, on_complete=None):
    run_in_background(_load_run_steps_thread, run_id, on_complete)


def _load_run_steps_thread(run_id, on_complete):
    try:
        steps = workflows.get_run_steps(run_id)
    except Exception:
        steps = None
    _emit_complete(on_complete, steps)


def _emit_complete(on_complete, payload):
    if on_complete:
        on_complete(payload)
