"""GitHub Actions workflow dispatch/polling calls.

Pure API-layer functions: given inputs, talk to GitHub and return data.
No business logic (retry policies, job bookkeeping, etc.) lives here -
that belongs in the services layer.
"""
import time

from api.github import client
from core.config import API_BASE, GITHUB_BRANCH


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
        items.append({
            "name": run.get("name") or run.get("display_title", "?"),
            "workflow": run.get("path", "").split("/")[-1],
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "created_at": run.get("created_at", "")[:16].replace("T", " "),
            "run_id": run.get("id"),
        })
    return items


def get_run_steps(run_id):
    """Fetches the step-by-step status of a run's first job, like the
    official GitHub Actions app shows."""
    url = f"{API_BASE}/actions/runs/{run_id}/jobs"
    r = client.get(url)
    jobs = r.json().get("jobs", [])
    if not jobs:
        return []
    return jobs[0].get("steps", [])