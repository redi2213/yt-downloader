"""The Actions browser behind "Latest GitHub Actions runs": every workflow of
the repo, one workflow's runs page by page, running a workflow by hand, and
getting a failed run's error text / full log to the clipboard or the phone.

Every ``start_*`` function works in the background and calls
``on_done(result_dict)`` from that thread (the caller hops onto the Kivy thread).
"""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from api.github import logs, releases, workflows
from core import android_downloads, cron_text, rerun
from core.async_utils import run_in_background
from core.exceptions import AuthenticationError

PAGE_SIZE = 15
STATUS_PAGE_SIZE = 20      # runs per page on the Actions status screen
_CRON_CACHE = {}           # workflow file -> its cron lines (read once per session)
_TOKEN_ERROR = "GitHub token invalid or expired. Update it and retry."

# Groups of the "by app menu" view: (title, [workflow files]). Anything not
# listed lands in "Other".
MENU_GROUPS = [
    ("YouTube", ["download.yml", "list-formats.yml", "list-playlist.yml"]),
    ("Aparat", ["aparat-download.yml"]),
    ("Download Anything", ["Any-Site-Upload.yml", "telegram-download.yml", "filimo-direct-link.yml",
                           "google-play-download.yml", "upload-file.yml", "Series-Links.yml",
                           "drive-to-release.yml"]),
    ("Auto follow", ["Auto-Follow.yml"]),
    ("Build and backup", ["build-apk.yml", "backup-project.yml"]),
    ("Maintenance", ["zip-release.yml", "cleanup-releases.yml", "cleanup-artifacts.yml"]),
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


def start_cancel_run(run_id, on_done):
    """Stops a run on GitHub (works for any run, also one the app did not start)."""
    def work():
        workflows.cancel_run(run_id)
        return {}
    run_in_background(_guarded, on_done, work)


# -- the Actions status screen: filters, clean-up, scheduled workflows ---------
def start_load_status(workflow_file, status, page, need_workflows, on_done):
    """One page of runs for the status screen (+ the workflow list when asked)."""
    def work():
        runs, has_next = workflows.get_status_runs(workflow_file, status, page, STATUS_PAGE_SIZE)
        out = {"runs": runs, "has_next": has_next, "page": page}
        if need_workflows:
            out["workflows"] = workflows.list_workflows()
        return out
    run_in_background(_safe, on_done, work)


def start_collect_cleanup(workflow_file, kind, days, on_done):
    """Ids of the runs a clean-up would delete: ``kind`` "failed" or "older"
    (finished runs created more than ``days`` days ago)."""
    def work():
        if kind == "failed":
            return {"ids": workflows.collect_run_ids(workflow_file, status="failure")}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        return {"ids": workflows.collect_run_ids(workflow_file, status="completed", created_before=cutoff)}
    run_in_background(_safe, on_done, work)


def _delete_one(run_id):
    try:
        workflows.delete_run(run_id)
        return True
    except Exception:
        return False


def start_delete_runs(run_ids, on_item, on_done):
    """Deletes the runs (4 at a time); ``on_item(run_id, ok)`` as each one finishes."""
    def work():
        deleted = failed = 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_delete_one, rid): rid for rid in run_ids}
            for future in as_completed(futures):
                ok = future.result()
                if ok:
                    deleted += 1
                else:
                    failed += 1
                on_item(futures[future], ok)
        return {"deleted": deleted, "failed": failed}
    run_in_background(_safe, on_done, work)


def start_load_schedules(on_done):
    """Every workflow with a cron schedule: ``{"file", "tool", "state", "crons"}``."""
    def work():
        items = workflows.list_workflows()

        def one(wf):
            crons = _CRON_CACHE.get(wf["file"])
            if crons is None:
                try:
                    crons = cron_text.find_crons(workflows.get_workflow_file_text(wf["file"]))
                except Exception:
                    return None
                _CRON_CACHE[wf["file"]] = crons
            return {**wf, "crons": crons} if crons else None

        with ThreadPoolExecutor(max_workers=6) as pool:
            found = [x for x in pool.map(one, items) if x]
        return {"schedules": found}
    run_in_background(_safe, on_done, work)


def start_toggle_workflow(workflow_file, enabled, on_done):
    def work():
        try:
            workflows.set_workflow_enabled(workflow_file, enabled)
            on_done({"ok": True})
        except Exception as e:
            on_done({"ok": False, "error": f"Could not change the workflow: {str(e)[:60]}"})
    run_in_background(work)
