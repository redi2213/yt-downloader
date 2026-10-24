"""Any site: "Check formats" - list what a site offers, then download one.

The Any-Site-Upload.yml workflow, started with quality "check", downloads
nothing: for every link it prints one ``FORMATS_JSON={...}`` line to the job
log (and a table to the run summary). This service starts that run, waits for
it, and reads those lines back, so the app can show the formats as buttons.
Downloading the chosen one is an ordinary run of the same workflow with the
``format_id`` input set (see generic_action_service._resolve_inputs).
"""
import json
import re

from api.github import logs, workflows
from core.async_utils import run_in_background
from core.exceptions import AuthenticationError
from services import runs_service

_FORMATS_RE = re.compile(r"FORMATS_JSON=(\{.*\})\s*$")
_LINK_JOB_RE = re.compile(r"^link\s+(\d+)", re.IGNORECASE)


# GitHub hides every "5" in a log when a secret's value is "5" (the digit becomes ***), which breaks the
# numbers of FORMATS_JSON. The workflow therefore also prints FORMATS_SAFE, the same JSON with each 5 sent
# as this sign; it is turned back before reading. FORMATS_SAFE is preferred, FORMATS_JSON is the fallback.
_SAFE_RE = re.compile(r"FORMATS_SAFE=(\{.*\})\s*$")
_FIVE_SIGN = "\u00a4"


def _collect(text, regex, decode):
    found = []
    for line in (text or "").splitlines():
        m = regex.search(line)
        if not m:
            continue
        raw = m.group(1).replace(_FIVE_SIGN, "5") if decode else m.group(1)
        try:
            payload = json.loads(raw)
        except ValueError:
            continue
        if isinstance(payload, dict) and payload.get("url"):
            found.append(payload)
    return found


def parse_formats_log(text):
    """The payload dicts found in a job log (usually one per link)."""
    return _collect(text, _SAFE_RE, True) or _collect(text, _FORMATS_RE, False)


def start_check(action, urls, on_status, on_done):
    """on_done(res) from a background thread:
    {'ok': True, 'run_id': id, 'links': [{url, title, heights, formats}]}
    or {'ok': False, 'error': str}. ``urls`` is the multi-line text of the form."""
    run_in_background(_check_thread, action, urls, on_status, on_done)


def _say(on_status, text):
    if on_status:
        on_status(text)


def _check_thread(action, urls, on_status, on_done):
    try:
        _say(on_status, "Starting the check...")
        inputs = {"mode": "release", "urls": urls, "quality": "check"}
        run_id = workflows.dispatch_and_find_run(action["workflow"], inputs)
        if run_id is None:
            on_done({"ok": False, "error": "Could not detect the workflow run. It may still be running on GitHub Actions."})
            return
        conclusion = workflows.wait_for_run(
            run_id, on_status=lambda s: _say(on_status, f"Checking formats ({s})..."))
        jobs = workflows.get_run_jobs(run_id)

        results = []
        for job in sorted(jobs, key=_job_order):
            if not _LINK_JOB_RE.match(job.get("name") or ""):
                continue
            text = logs.get_job_log_text(job["id"])
            results.extend(parse_formats_log(text))

        if results:
            on_done({"ok": True, "run_id": run_id, "links": results})
            return

        on_done({"ok": False, "run_id": run_id, "error": _failure_text(run_id, conclusion, jobs)})
    except AuthenticationError:
        on_done({"ok": False, "error": "GitHub token invalid or expired. Update it and retry."})
    except Exception as e:
        on_done({"ok": False, "error": f"Error: {str(e)[:80]}"})


def _job_order(job):
    m = _LINK_JOB_RE.match(job.get("name") or "")
    return int(m.group(1)) if m else 10 ** 6


def _failure_text(run_id, conclusion, jobs):
    """Why no format list came back: the run's error lines when it failed."""
    try:
        failed, _step = runs_service.find_failure(jobs)
        if failed is not None:
            text = logs.get_job_log_text(failed["id"])
            if text:
                return runs_service.extract_error(text, max_lines=12)
    except Exception:
        pass
    if conclusion == "success":
        return ("The check finished but no format list was found in the log. "
                "Is Any-Site-Upload.yml the new version (with the 'check' option)?")
    return f"The check failed ({conclusion})."
