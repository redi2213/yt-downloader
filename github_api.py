"""GitHub Actions / Releases API helpers used by the YT Bridge Git app.

Kept separate from main.py (the Kivy UI) so the API logic can be read,
tested, and modified independently of the screen/widget code.
"""
import time
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

REPO_OWNER = "redi2213"
REPO_NAME = "yt-downloader"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
APP_VERSION = "1.3"
# GitHub Actions free tier allows ~20 concurrent jobs; stay under that so
# dispatched runs don't queue behind each other.
MAX_PARALLEL_JOBS = 5

REQUEST_TIMEOUT = 15  # seconds; avoids requests hanging forever on flaky mobile networks


def _build_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


http = _build_session()

try:
    from plyer import notification
    HAS_NOTIFY = True
except Exception:
    HAS_NOTIFY = False


def notify(title, message):
    if HAS_NOTIFY:
        try:
            notification.notify(title=title, message=message, timeout=5)
        except Exception:
            pass


# --- Token storage -----------------------------------------------------
# Uses Kivy's JsonStore, but this module doesn't otherwise depend on Kivy.
from kivy.storage.jsonstore import JsonStore  # noqa: E402

settings_store = JsonStore("ytdl_settings.json")


def get_token():
    if settings_store.exists("github"):
        return settings_store.get("github")["token"]
    return ""


def save_token(token):
    settings_store.put("github", token=token)


def headers():
    return {"Authorization": f"token {get_token()}", "Accept": "application/vnd.github+json"}


class GitHubAuthError(Exception):
    """Raised when the GitHub token is missing, invalid, or lacks permissions."""
    pass


def _check_response(r):
    if r.status_code in (401, 403):
        raise GitHubAuthError(
            "GitHub token is invalid, expired, or missing required permissions."
        )
    r.raise_for_status()


def dispatch_workflow(workflow_file, inputs):
    """Dispatch a workflow and return the UTC timestamp (ISO, second precision)
    just before dispatch, so the caller can reliably find *this* run afterwards
    instead of guessing "the latest run belongs to me"."""
    dispatch_time = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    url = f"{API_BASE}/actions/workflows/{workflow_file}/dispatches"
    r = http.post(url, headers=headers(), json={"ref": "main", "inputs": inputs}, timeout=REQUEST_TIMEOUT)
    _check_response(r)
    return dispatch_time


def get_run_id_after(workflow_file, dispatch_time, attempts=10, delay=1.5):
    """Poll for the run created at/after dispatch_time, instead of blindly
    trusting 'most recent run' (which can grab someone else's run if two
    dispatches happen close together)."""
    url = f"{API_BASE}/actions/workflows/{workflow_file}/runs?per_page=5"
    for _ in range(attempts):
        r = http.get(url, headers=headers(), timeout=REQUEST_TIMEOUT)
        _check_response(r)
        runs = r.json().get("workflow_runs", [])
        for run in runs:
            created_at = run.get("created_at", "").rstrip("Z")
            if created_at >= dispatch_time:
                return run["id"]
        time.sleep(delay)
    return None


def get_run_id_by_job_id(workflow_file, job_id, attempts=20, delay=2):
    """Finds the run whose display name/title equals job_id. Used for
    upload-file.yml, where the workflow's job name is set to the job_id
    input - a more reliable match than dispatch-time comparison since it's
    a unique UUID rather than a timestamp that could theoretically collide."""
    url = f"{API_BASE}/actions/workflows/{workflow_file}/runs?per_page=20"
    for _ in range(attempts):
        r = http.get(url, headers=headers(), timeout=REQUEST_TIMEOUT)
        _check_response(r)
        runs = r.json().get("workflow_runs", [])
        for run in runs:
            if run.get("display_title") == job_id or run.get("name") == job_id:
                return run["id"]
        time.sleep(delay)
    return None


def wait_for_run(run_id, on_status=None, poll_interval=3, stop_event=None):
    """Polls until the run completes. If stop_event is set while waiting,
    returns "cancelled_locally" without cancelling the run on GitHub itself
    (use cancel_run for that)."""
    url = f"{API_BASE}/actions/runs/{run_id}"
    last_status = None
    while True:
        if stop_event is not None and stop_event.is_set():
            return "cancelled_locally"
        r = http.get(url, headers=headers(), timeout=REQUEST_TIMEOUT)
        _check_response(r)
        data = r.json()
        status = data["status"]
        if on_status and status != last_status:
            on_status(status)
            last_status = status
        if status == "completed":
            return data["conclusion"]
        time.sleep(poll_interval)


def cancel_run(run_id):
    """Actually cancels the workflow run on GitHub Actions (not just local polling)."""
    url = f"{API_BASE}/actions/runs/{run_id}/cancel"
    r = http.post(url, headers=headers(), timeout=REQUEST_TIMEOUT)
    _check_response(r)


def get_run_log_text(run_id):
    url = f"{API_BASE}/actions/runs/{run_id}/jobs"
    r = http.get(url, headers=headers(), timeout=REQUEST_TIMEOUT)
    _check_response(r)
    jobs = r.json().get("jobs", [])
    if not jobs:
        return ""
    job_id = jobs[0]["id"]
    log_url = f"{API_BASE}/actions/jobs/{job_id}/logs"
    r = http.get(log_url, headers=headers(), timeout=REQUEST_TIMEOUT)
    _check_response(r)
    return r.text


def parse_formats(log_text):
    results = []
    for line in log_text.splitlines():
        if "video only" not in line or "storyboard" in line:
            continue
        clean = re.sub(r"^.*Z ", "", line)
        parts = clean.split()
        if not parts:
            continue
        fmt_id = parts[0]
        m = re.search(r"(\d+p\d*)( HDR)?", clean)
        if not m:
            continue
        # yt-dlp's -F output includes an approximate size like "~ 15.50MiB" or
        # "77.16MiB" in one of the columns - grab it if present so it can be
        # shown next to the quality option.
        size_match = re.search(r"(?:~\s*)?(\d+(?:\.\d+)?)\s*(KiB|MiB|GiB)", clean)
        size_label = f"{size_match.group(1)}{size_match.group(2)}" if size_match else None
        results.append((fmt_id, m.group(0), size_label))
    return results


def get_release_link(run_id=None, tag=None, attempts=10, delay=2):
    if tag is None:
        tag = f"run-{run_id}"
    url = f"{API_BASE}/releases/tags/{tag}"
    for _ in range(attempts):
        r = http.get(url, headers=headers(), timeout=REQUEST_TIMEOUT)
        if r.status_code in (401, 403):
            raise GitHubAuthError("GitHub token is invalid or lacks permission to read releases.")
        if r.status_code == 200:
            assets = r.json().get("assets", [])
            if assets:
                return assets[0]["browser_download_url"]
        time.sleep(delay)
    return None


def get_recent_runs(limit=10):
    """Fetches the most recent workflow runs across all our workflow files
    combined, sorted newest first - used for the always-available status
    check that doesn't depend on the app's own current_job tracking."""
    url = f"{API_BASE}/actions/runs?per_page={limit}"
    r = http.get(url, headers=headers(), timeout=REQUEST_TIMEOUT)
    _check_response(r)
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


def get_playlist_links(playlist_url):
    dispatch_time = dispatch_workflow("list-playlist.yml", {"playlist_url": playlist_url})
    run_id = get_run_id_after("list-playlist.yml", dispatch_time)
    if run_id is None:
        return []
    conclusion = wait_for_run(run_id)
    if conclusion != "success":
        return []
    log_text = get_run_log_text(run_id)
    urls = re.findall(r"https://(?:www\.)?youtube\.com/watch\?v=[\w-]+|https://youtu\.be/[\w-]+", log_text)
    return list(dict.fromkeys(urls))


def get_live_history():
    url = f"{API_BASE}/releases?per_page=30"
    r = http.get(url, headers=headers(), timeout=REQUEST_TIMEOUT)
    _check_response(r)
    releases = r.json()
    items = []
    for rel in releases:
        tag = rel.get("tag_name", "")
        if not (tag.startswith("run-") or tag.startswith("job-")):
            continue
        assets = rel.get("assets", [])
        if not assets:
            continue
        items.append({
            "title": assets[0]["name"],
            "link": assets[0]["browser_download_url"],
            "date": rel.get("created_at", "")[:16].replace("T", " "),
            "release_id": rel["id"],
            "asset_id": assets[0]["id"],
            "tag_name": tag,
            "size": assets[0].get("size", 0),
        })
    return items


def delete_release(release_id, tag_name):
    """Deletes the release and its underlying git tag so it doesn't linger."""
    url = f"{API_BASE}/releases/{release_id}"
    r = http.delete(url, headers=headers(), timeout=REQUEST_TIMEOUT)
    _check_response(r)
    # Best-effort: also remove the tag itself (release deletion alone leaves it behind)
    tag_url = f"{API_BASE}/git/refs/tags/{tag_name}"
    try:
        http.delete(tag_url, headers=headers(), timeout=REQUEST_TIMEOUT)
    except Exception:
        pass


def rename_release_asset(release_id, asset_id, new_filename):
    """Renames an existing release asset in place via GitHub's asset-update API
    (no need to re-download/re-upload the file)."""
    url = f"{API_BASE}/releases/assets/{asset_id}"
    r = http.patch(url, headers=headers(), json={"name": new_filename}, timeout=REQUEST_TIMEOUT)
    _check_response(r)
    return r.json().get("browser_download_url")
