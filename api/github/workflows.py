"""GitHub Actions workflow dispatch/polling calls.

Pure API-layer functions: given inputs, talk to GitHub and return data.
No business logic (retry policies, job bookkeeping, etc.) lives here -
that belongs in the services layer.
"""
import re
import threading
import time
import uuid

import requests

from api.github import client
from core import run_labels, run_title, timeutil
from core.config import API_BASE, GITHUB_BRANCH

# Name of the optional workflow input the app fills with a unique token. A
# workflow that declares it and puts it in its ``run-name`` lets the app find
# exactly the run it dispatched, however many links are sent at once.
RUN_TOKEN_INPUT = "job_id"
# Optional second input: a short ASCII name for the run (see core/run_title.py)
RUN_TITLE_INPUT = "run_title"

# Only used for workflows that don't know the token input yet: dispatch + find
# must not overlap, otherwise two quick dispatches can pick each other's run.
_legacy_lock = threading.Lock()

# Runs this app already matched to one of its jobs. A time-based lookup skips
# them: GitHub timestamps have one-second resolution, so a run created in the
# same second as the NEXT dispatch would otherwise look like the new one.
_claimed_runs = set()

# "...[a1b2c3d4e5f6]" suffix added by run-name; hidden in run lists.
_TOKEN_SUFFIX_RE = re.compile(r"\s*\[[0-9a-f]{12}\]\s*$")


def dispatch_workflow(workflow_file: str, inputs: dict) -> str:
    """Dispatch a workflow and return the UTC timestamp (ISO, second
    precision) just before dispatch, so the caller can reliably find *this*
    run afterwards instead of guessing "the latest run belongs to me".

    ref is GITHUB_BRANCH, not hardcoded - every workflow this app dispatches
    (list-formats, list-playlist, download, upload-file, ...) runs on
    whichever branch this specific APK was built from, since they all funnel
    through this one function."""
    dispatch_time = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    url = f"{API_BASE}/actions/workflows/{workflow_file}/dispatches"
    client.post(url, json={"ref": GITHUB_BRANCH, "inputs": inputs})
    return dispatch_time


def get_run_id_after(workflow_file: str, dispatch_time: str, attempts: int = 10, delay: float = 1.5):
    """Poll for the run created at/after dispatch_time, instead of blindly
    trusting 'most recent run' (which can grab someone else's run if two
    dispatches happen close together)."""
    url = f"{API_BASE}/actions/workflows/{workflow_file}/runs?per_page=5"
    for _ in range(attempts):
        r = client.get(url)
        runs = r.json().get("workflow_runs", [])
        for run in runs:
            created_at = run.get("created_at", "").rstrip("Z")
            if created_at >= dispatch_time:
                return run["id"]
        time.sleep(delay)
    return None


def get_run_id_by_token(workflow_file: str, token: str, attempts: int = 12, delay: float = 1.5):
    """Finds the run whose title (the workflow's ``run-name``) contains
    ``token``."""
    url = f"{API_BASE}/actions/workflows/{workflow_file}/runs?per_page=20"
    for _ in range(attempts):
        r = client.get(url)
        runs = r.json().get("workflow_runs", [])
        for run in runs:
            title = f"{run.get('display_title') or ''} {run.get('name') or ''}"
            if token in title:
                return run["id"]
        time.sleep(delay)
    return None


def _find_unclaimed_run_after(workflow_file: str, dispatch_time: str, attempts: int, delay: float):
    """Time-based lookup that ignores runs already claimed by another job and
    takes the OLDEST new one (the first run created after our dispatch)."""
    url = f"{API_BASE}/actions/workflows/{workflow_file}/runs?per_page=10"
    for _ in range(attempts):
        r = client.get(url)
        runs = r.json().get("workflow_runs", [])
        candidates = [
            run for run in runs
            if run.get("created_at", "").rstrip("Z") >= dispatch_time
            and run["id"] not in _claimed_runs
        ]
        if candidates:
            run_id = candidates[-1]["id"]  # runs are listed newest first
            _claimed_runs.add(run_id)
            return run_id
        time.sleep(delay)
    return None


def _dispatch_and_find_legacy(workflow_file: str, inputs: dict, attempts: int, delay: float):
    with _legacy_lock:
        dispatch_time = dispatch_workflow(workflow_file, inputs)
        return _find_unclaimed_run_after(workflow_file, dispatch_time, attempts, delay)


def dispatch_and_find_run(workflow_file: str, inputs: dict, attempts: int = 12, delay: float = 1.5):
    """Dispatches a workflow and returns the id of exactly that run (or None
    if it can't be found).

    A unique token is sent as the ``job_id`` input and matched against the
    run's title, so several links dispatched at once never get mixed up.
    Workflows that don't declare that input yet answer HTTP 422; for those the
    old time-based matching is used, serialised by a lock."""
    # A caller that already owns a job_id (the upload flow tags its release
    # with it) keeps it; it becomes the token.
    token = inputs.get(RUN_TOKEN_INPUT) or uuid.uuid4().hex[:12]
    tagged = dict(inputs)
    tagged[RUN_TOKEN_INPUT] = token
    title = inputs.get(RUN_TITLE_INPUT) or run_title.build_title(inputs)
    dispatch_time = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    url = f"{API_BASE}/actions/workflows/{workflow_file}/dispatches"

    # Newest workflow first: token + title; then token only; then (a workflow
    # that knows neither input answers HTTP 422 each time) the old way.
    payloads = []
    if title:
        payloads.append({**tagged, RUN_TITLE_INPUT: title})
    payloads.append(tagged)
    for payload in payloads:
        try:
            client.post(url, json={"ref": GITHUB_BRANCH, "inputs": payload})
            break
        except requests.exceptions.HTTPError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status != 422:
                raise
    else:
        return _dispatch_and_find_legacy(workflow_file, inputs, attempts, delay)

    # The title carries the token almost at once when the workflow has the new
    # run-name, so this search is short; the long search below only matters
    # for a workflow whose run-name doesn't show the token yet.
    run_id = get_run_id_by_token(workflow_file, token, min(attempts, 10), min(delay, 1.5))
    if run_id is not None:
        _claimed_runs.add(run_id)
        return run_id
    # Workflow accepted the input but its run-name doesn't show it.
    with _legacy_lock:
        return _find_unclaimed_run_after(workflow_file, dispatch_time, attempts, delay)


def get_run_id_by_job_id(workflow_file: str, job_id: str, attempts: int = 20, delay: float = 2):
    """Finds the run whose display name/title equals job_id. Used for
    upload-file.yml, where the workflow's job name is set to the job_id
    input - a more reliable match than dispatch-time comparison since it's
    a unique UUID rather than a timestamp that could theoretically collide."""
    url = f"{API_BASE}/actions/workflows/{workflow_file}/runs?per_page=20"
    for _ in range(attempts):
        r = client.get(url)
        runs = r.json().get("workflow_runs", [])
        for run in runs:
            if run.get("display_title") == job_id or run.get("name") == job_id:
                return run["id"]
        time.sleep(delay)
    return None


def wait_for_run(run_id, on_status=None, poll_interval: float = 3, stop_event=None):
    """Polls until the run completes. If stop_event is set while waiting,
    returns "cancelled_locally" without cancelling the run on GitHub itself
    (use cancel_run for that)."""
    url = f"{API_BASE}/actions/runs/{run_id}"
    last_status = None
    while True:
        if stop_event is not None and stop_event.is_set():
            return "cancelled_locally"
        r = client.get(url)
        data = r.json()
        status = data["status"]
        if on_status and status != last_status:
            on_status(status)
            last_status = status
        if status == "completed":
            return data["conclusion"]
        time.sleep(poll_interval)


def cancel_run(run_id) -> None:
    """Actually cancels the workflow run on GitHub Actions (not just local polling)."""
    url = f"{API_BASE}/actions/runs/{run_id}/cancel"
    client.post(url)


def get_recent_runs(limit: int = 10):
    """Fetches the most recent workflow runs across all our workflow files
    combined, sorted newest first - used for the always-available status
    check that doesn't depend on the app's own current-job tracking."""
    url = f"{API_BASE}/actions/runs?per_page={limit}"
    r = client.get(url)
    runs = r.json().get("workflow_runs", [])
    items = []
    for run in runs:
        raw_name = run.get("name") or run.get("display_title", "?")
        had_token = bool(_TOKEN_SUFFIX_RE.search(raw_name))
        name = _TOKEN_SUFFIX_RE.sub("", raw_name)
        workflow = run.get("path", "").split("/")[-1]
        items.append({
            "name": name,
            "workflow": workflow,
            "tool": run_labels.tool_label(workflow),
            # a run named by the app carries its title (or link) in its name;
            # a plain workflow name ("Download Video") says nothing new
            "short_title": run_labels.short_title(name) or (run_labels.clip_title(name) if had_token else ""),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "created_at": timeutil.utc_iso_to_local(run.get("created_at"), "%m-%d %H:%M"),
            "run_id": run.get("id"),
        })
    return items


def get_run_jobs(run_id):
    """Every job of a run with its steps (number, name, status, conclusion and
    start/end times) - what the run detail and progress panels show."""
    url = f"{API_BASE}/actions/runs/{run_id}/jobs?per_page=30"
    r = client.get(url)
    jobs = []
    for job in r.json().get("jobs", []):
        jobs.append({
            "id": job.get("id"),
            "name": job.get("name"),
            "status": job.get("status"),
            "conclusion": job.get("conclusion"),
            "steps": [
                {
                    "number": step.get("number"),
                    "name": step.get("name", "?"),
                    "status": step.get("status"),
                    "conclusion": step.get("conclusion"),
                    "started_at": step.get("started_at"),
                    "completed_at": step.get("completed_at"),
                }
                for step in job.get("steps", [])
            ],
        })
    return jobs


def get_run_steps(run_id):
    """Fetches the step-by-step status of a run's first job, like the
    official GitHub Actions app shows."""
    url = f"{API_BASE}/actions/runs/{run_id}/jobs"
    r = client.get(url)
    jobs = r.json().get("jobs", [])
    if not jobs:
        return []
    return jobs[0].get("steps", [])