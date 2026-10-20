"""The Actions browser behind "Latest GitHub Actions runs": every workflow of
the repo, one workflow's runs page by page, running a workflow by hand, and
getting a failed run's error text / full log to the clipboard or the phone.

Every ``start_*`` function works in the background and calls
``on_done(result_dict)`` from that thread (the caller hops onto the Kivy thread).
"""
import re

from api.github import logs, releases, workflows
from core import android_downloads, rerun
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
                           "google-play-download.yml", "upload-file.yml", "Series-Links.yml"]),
    ("Auto follow", ["Auto-Follow.yml"]),
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


def start_log_text(run_id, jobs, on_done):
    """The cleaned log (last 400 lines) of the failed job, or of the first job."""
    def work():
        job, _step = find_failure(jobs)
        job = job or next(iter(jobs or []), None)
        if job is None:
            raise ValueError("No job to read a log from.")
        text = logs.get_job_log_text(job["id"])
        if text is None:
            raise ValueError("GitHub has no log for this job (yet). Try again in a minute.")
        lines = [_TIME_PREFIX.sub("", l).rstrip() for l in text.splitlines()]
        return {"text": _header(run_id, job, None) + "\n\n" + "\n".join(lines[-400:])}
    run_in_background(_guarded, on_done, work)


def start_run_result(run_id, on_done):
    """What a finished run left behind: its release's link(s), like the result
    screen of the job that started it. Fails clearly when the run made no release."""
    def work():
        link = releases.get_release_result(run_id, attempts=1, delay=0)
        links = releases.get_release_links(run_id, attempts=1, delay=0)
        extras = releases.get_release_extras(run_id)
        if not link and not links:
            raise ValueError("This run left no files (it made no release, or it is still running).")
        return {"link": link, "links": links if len(links) > 1 else None, **extras}
    run_in_background(_guarded, on_done, work)


# -- Run again -----------------------------------------------------------------
def start_rerun_plan(run_id, on_done):
    """Reads what is needed to repeat a run. The result is one of

    * ``{"ok": True, "exact": True, "workflow", "inputs"}``  - the run's own
      inputs were found in its name: it can be sent again as it is;
    * ``{"ok": True, "exact": False, "workflow", "prefill", "tool"}`` - they
      were not (an older run, or one started on GitHub): ``prefill`` is the
      text for the manual-run box (``name=value`` lines).
    """
    def work():
        info = workflows.get_run_info(run_id)
        file = info["workflow"]
        if not file:
            raise ValueError("Could not tell which workflow this run belongs to.")
        inputs = rerun.inputs_from_name(info["name"])
        if inputs is not None:
            return {"exact": True, "workflow": file, "inputs": inputs}
        title = rerun.split_run_name(info["name"])[0]
        try:
            declared = rerun.parse_declared_inputs(workflows.get_workflow_file_text(file))
        except Exception:
            declared = []
        return {"exact": False, "workflow": file, "tool": run_labels_tool(file),
                "prefill": rerun.prefill_lines(file, title, declared)}
    run_in_background(_guarded, on_done, work)


def run_labels_tool(file):
    from core import run_labels
    return run_labels.tool_label(file)


def start_rerun_dispatch(workflow_file, inputs, on_done):
    """Sends ``workflow_file`` again with ``inputs`` (the app adds a fresh
    token and the current storage choice, like for any other run)."""
    def work():
        try:
            run_id = workflows.dispatch_and_find_run(workflow_file, dict(inputs))
        except Exception as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code == 422:
                raise ValueError("GitHub refused the inputs. Use the manual run page and check them.")
            raise
        return {"run_id": run_id}
    run_in_background(_guarded, on_done, work)
