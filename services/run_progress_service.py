"""What a run is doing right now: its steps and the last lines of its log.

Used by the progress panel on the working screen and by the per-step log
screen. Both work with whatever GitHub has: step status comes from the jobs
API; log text comes from the job-log endpoint, which may lag behind or not
have a running step's output yet - then the lines are simply missing.
"""
from api.github import logs, workflows
from core import run_log
from core.async_utils import run_in_background
from core.exceptions import AuthenticationError

_TOKEN_ERROR = "GitHub token invalid or expired. Update it and retry."
_STEP_TAIL_LINES = 15


def _current_job(jobs):
    """The job being watched: the first one still running, else the last."""
    for job in jobs:
        if job.get("status") != "completed":
            return job
    return jobs[-1] if jobs else None


def _entries(job):
    """Parsed log of a job, or None when GitHub has no log for it."""
    try:
        text = logs.get_job_log_text(job["id"])
    except AuthenticationError:
        raise
    except Exception:
        return None
    if not text:
        return None
    return run_log.parse_log(text)


def start_load_progress(run_id, on_complete=None):
    run_in_background(_progress_thread, run_id, on_complete)


def _progress_thread(run_id, on_complete):
    try:
        jobs = workflows.get_run_jobs(run_id)
        job = _current_job(jobs)
        entries = _entries(job) if job else None
        payload = {
            "ok": True,
            "jobs": jobs,
            "job": job,
            "log_available": entries is not None,
            "last_line": run_log.clip(run_log.last_line(entries), 120) if entries else None,
        }
    except AuthenticationError:
        payload = {"ok": False, "error": _TOKEN_ERROR}
    except Exception as e:
        payload = {"ok": False, "error": f"Could not load progress: {str(e)[:50]}"}
    _emit(on_complete, payload)


def start_load_step_view(run_id, job_id, step_number, on_complete=None):
    run_in_background(_step_view_thread, run_id, job_id, step_number, on_complete)


def _step_view_thread(run_id, job_id, step_number, on_complete):
    try:
        jobs = workflows.get_run_jobs(run_id)
        job = next((j for j in jobs if j["id"] == job_id), None)
        step = None
        if job:
            step = next((s for s in job["steps"] if s["number"] == step_number), None)
        if job is None or step is None:
            payload = {"ok": False, "error": "Could not find that step"}
        else:
            entries = _entries(job)
            lines = []
            if entries is not None:
                lines = run_log.tail(run_log.step_lines(entries, job["steps"], step_number),
                                     _STEP_TAIL_LINES)
            payload = {
                "ok": True,
                "job": job,
                "step": step,
                "log_available": entries is not None,
                "lines": [run_log.clip(line, 160) for line in lines],
            }
    except AuthenticationError:
        payload = {"ok": False, "error": _TOKEN_ERROR}
    except Exception as e:
        payload = {"ok": False, "error": f"Could not load step: {str(e)[:50]}"}
    _emit(on_complete, payload)


def _emit(on_complete, payload):
    if on_complete:
        on_complete(payload)
