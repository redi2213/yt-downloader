"""The Actions browser behind "Latest GitHub Actions runs": every workflow of
the repo, one workflow's runs page by page, running a workflow by hand, and
getting a failed run's error text / full log to the clipboard or the phone.

Every ``start_*`` function works in the background and calls
``on_done(result_dict)`` from that thread (the caller hops onto the Kivy thread).
"""
import re

from api.github import logs, workflows
from core import android_downloads
from core.async_utils import run_in_background
from core.exceptions import AuthenticationError

PAGE_SIZE = 15
_TOKEN_ERROR = "GitHub token invalid or expired. Update it and retry."

# Groups of the "by app menu" view: (title, [workflow files]). Anything not
# listed lands in "Other".
MENU_GROUPS = [
    ("YouTube", ["download.yml", "list-formats.yml", "list-playlist.yml"]),
    ("Aparat", ["aparat-download.yml"]),
    ("Download Anything", ["Any-Site-Upload.yml", "telegram-download.yml", "filimo-direct-link.yml",
                           "google-play-download.yml", "upload-file.yml"]),
    ("Build and backup", ["build-apk.yml", "backup-project.yml"]),
    ("Maintenance", ["zip-release.yml", "cleanup-releases.yml", "arvan-maintenance.yml"]),
]
OTHER_GROUP = "Other"


def group_workflows(items):
    """[(group title, [workflow dicts])] for the workflows that exist, in menu
    order; unknown files go to the last group."""
    by_file = {w["file"]: w for w in items}
    used, groups = set(), []
    for title, files in MENU_GROUPS:
        found = [by_file[f] for f in files if f in by_file]
        used.update(w["file"] for w in found)
        if found:
            groups.append((title, found))
    rest = [w for w in items if w["file"] not in used]
    if rest:
        groups.append((OTHER_GROUP, rest))
    return groups


def _error_text(e):
    if isinstance(e, AuthenticationError):
        return _TOKEN_ERROR
    return f"Could not load: {str(e)[:70]}"


def _safe(on_done, fn):
    try:
        on_done({"ok": True, **fn()})
    except Exception as e:
        on_done({"ok": False, "error": _error_text(e)})


def start_load_workflows(on_done):
    run_in_background(_safe, on_done, lambda: {"workflows": workflows.list_workflows()})


def start_load_runs(workflow_file, page, on_done):
    def work():
        runs, has_next = workflows.get_workflow_runs(workflow_file, page, PAGE_SIZE)
        return {"runs": runs, "has_next": has_next, "page": page}
    run_in_background(_safe, on_done, work)


# -- run a workflow by hand ----------------------------------------------------
def parse_inputs(text):
    """'name=value' lines -> (dict, error text or None). Empty lines and
    lines starting with # are ignored."""
    inputs = {}
    for number, line in enumerate((text or "").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            return {}, f"Line {number} needs the form name=value"
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", key):
            return {}, f"Line {number}: \"{key}\" is not a valid input name"
        inputs[key] = value.strip()
    return inputs, None


def start_manual_run(workflow_file, inputs, on_done):
    def work():
        try:
            dispatch_time = workflows.dispatch_manual(workflow_file, inputs)
        except Exception as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code == 422:
                raise ValueError("GitHub refused the inputs (a wrong name, or this workflow "
                                 "cannot be started by hand).")
            raise
        run_id = workflows.get_run_id_after(workflow_file, dispatch_time, attempts=8, delay=1.5)
        return {"run_id": run_id}
    run_in_background(_guarded, on_done, work)


# -- failed run: error text and full log ----------------------------------------
_TIME_PREFIX = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ?")
_FAILED = ("failure", "timed_out", "startup_failure")


def find_failure(jobs):
    """(job, failed step or None) of the first failed job, or (None, None)."""
    for job in jobs or []:
        if job.get("conclusion") in _FAILED:
            step = next((s for s in job.get("steps", []) if s.get("conclusion") in _FAILED), None)
            return job, step
    return None, None


def has_failure(jobs):
    return find_failure(jobs)[0] is not None


def extract_error(log_text, max_lines=60):
    """The error lines of a job log, each with 3 lines of context before it
    (GitHub marks them ##[error]); the last 40 lines when none is marked."""
    lines = [_TIME_PREFIX.sub("", l).rstrip() for l in (log_text or "").splitlines()]
    marks = [i for i, l in enumerate(lines) if "##[error]" in l]
    if not marks:
        return "\n".join(lines[-40:])
    keep = []
    for i in marks:
        for j in range(max(0, i - 3), i + 1):
            if j not in keep:
                keep.append(j)
    keep.sort()
    out = [lines[j].replace("##[error]", "ERROR: ") for j in keep]
    return "\n".join(out[-max_lines:])


def _header(run_id, job, step):
    parts = [f"Run #{run_id}", f"Job: {job.get('name') or '?'}"]
    if step:
        parts.append(f"Failed step: {step.get('name')} (#{step.get('number')})")
    return "\n".join(parts)


def start_error_text(run_id, jobs, on_done):
    def work():
        job, step = find_failure(jobs)
        if job is None:
            raise ValueError("This run has no failed step.")
        text = logs.get_job_log_text(job["id"])
        if text is None:
            raise ValueError("GitHub has no log for this job (yet). Try again in a minute.")
        return {"text": _header(run_id, job, step) + "\n\n" + extract_error(text)}
    run_in_background(_guarded, on_done, work)


def start_save_log(run_id, jobs, on_done):
    def work():
        job, step = find_failure(jobs)
        job = job or next(iter(jobs or []), None)
        if job is None:
            raise ValueError("No job to save a log for.")
        text = logs.get_job_log_text(job["id"])
        if text is None:
            raise ValueError("GitHub has no log for this job (yet). Try again in a minute.")
        clean = "\n".join(_TIME_PREFIX.sub("", l) for l in text.splitlines())
        name = android_downloads.safe_file_name(f"run-{run_id}-{job.get('name') or 'job'}.txt")
        saved = android_downloads.save_text_file(_header(run_id, job, step) + "\n\n" + clean, name, "Logs")
        return {"saved": str(saved)}
    run_in_background(_guarded, on_done, work)


def _guarded(on_done, work):
    try:
        on_done({"ok": True, **work()})
    except ValueError as e:
        on_done({"ok": False, "error": str(e)})
    except Exception as e:
        on_done({"ok": False, "error": _error_text(e)})
