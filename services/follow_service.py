"""Auto follow: reading and saving the followed channels, starting a check now,
and listing each channel's files.

* ``follows.json`` / ``follow-state.json`` live on the ``config`` branch. The app
  writes the first; the Auto-Follow.yml workflow (scripts/auto_follow.py) writes
  the second, so the two never overwrite each other.
* The files of a channel are the assets of its release ``auto-<slug>``.
* Saving also rewrites the cron line of ``.github/workflows/Auto-Follow.yml`` on
  the repo's default branch (scheduled workflows only run from there) so the
  scheduler wakes up only in the hours the time windows need.
"""
import base64
import json

from api import follow_prefs
from api.github import client, releases, repo_files, workflows
from api.github.auth import auth_headers
from core import follow as follow_core
from core.async_utils import run_in_background
from core.config import API_BASE
from core.exceptions import AuthenticationError

CONFIG_BRANCH = "config"
FOLLOWS_FILE = "follows.json"
STATE_FILE = "follow-state.json"
WORKFLOW_FILE = "Auto-Follow.yml"


def _error_text(e):
    if isinstance(e, AuthenticationError):
        return "GitHub token invalid, expired or not allowed to do this."
    return f"Error: {str(e)[:80]}"


def _guarded(on_done, work):
    try:
        on_done({"ok": True, **work()})
    except ValueError as e:
        on_done({"ok": False, "error": str(e)})
    except Exception as e:
        on_done({"ok": False, "error": _error_text(e)})


def _read_json(path, default):
    headers = dict(auth_headers())
    headers["Accept"] = "application/vnd.github.raw+json"
    r = client.get_allow_missing(f"{API_BASE}/contents/{path}", params={"ref": CONFIG_BRANCH}, headers=headers)
    if r.status_code != 200:
        return default
    try:
        data = json.loads(r.text)
    except ValueError:
        return default
    return data if isinstance(data, type(default)) else default


def load():
    cfg = _read_json(FOLLOWS_FILE, {})
    return list(cfg.get("follows") or []), _read_json(STATE_FILE, {})


def start_load(on_done):
    """``on_done({"ok", "follows", "state"})``."""
    def work():
        follows, state = load()
        return {"follows": follows, "state": state}
    run_in_background(_guarded, on_done, work)


def _asset_names(follow):
    return [a["name"] for a in releases.get_release_assets(follow_core.release_tag(follow), attempts=1, delay=0)]


def start_overview(on_done):
    """Follows + state + how many files of each channel are new (not seen yet)."""
    def work():
        follows, state = load()
        new = {}
        for f in follows:
            try:
                tag = follow_core.release_tag(f)
                names = _asset_names(f)
                new[f["id"]] = len([n for n in names if n not in follow_prefs.get_seen(tag)])
            except Exception:
                new[f["id"]] = 0
        return {"follows": follows, "state": state, "new": new}
    run_in_background(_guarded, on_done, work)


def start_files(follow, on_done):
    """The files of the channel's release, newest last, as ``{"assets": [...], "links": [...]}``."""
    def work():
        tag = follow_core.release_tag(follow)
        assets = releases.get_release_assets(tag, attempts=1, delay=0)
        if not assets:
            raise ValueError("No files yet. They appear here after the first download finishes.")
        r = client.get_allow_missing(f"{API_BASE}/releases/tags/{tag}")
        links = [a["browser_download_url"] for a in (r.json().get("assets", []) if r.status_code == 200 else [])]
        follow_prefs.set_seen(tag, [a["name"] for a in assets])
        return {"assets": assets, "links": links, "tag": tag}
    run_in_background(_guarded, on_done, work)


def _default_branch():
    return client.get(API_BASE).json().get("default_branch") or "main"


def sync_schedule(follows):
    """Rewrites the cron line of Auto-Follow.yml on the default branch. Returns
    (ok, message); never raises (a token without the 'workflow' permission is common)."""
    cron = follow_core.cron_for(follows)
    try:
        branch = _default_branch()
        url = f"{API_BASE}/contents/.github/workflows/{WORKFLOW_FILE}"
        r = client.get_allow_missing(url, params={"ref": branch})
        if r.status_code != 200:
            return False, f"{WORKFLOW_FILE} is not on the {branch} branch: send the update zip first."
        data = r.json()
        text = base64.b64decode(data["content"]).decode("utf-8")
        new = follow_core.with_cron(text, cron)
        if new is None:
            return False, "The schedule line was not found in Auto-Follow.yml."
        if new == text:
            return True, f"Schedule already up to date ({follow_core.ticks_per_day(cron)} wake-ups a day)."
        client.request("PUT", url, json={
            "message": "Auto follow: update the schedule", "branch": branch, "sha": data["sha"],
            "content": base64.b64encode(new.encode("utf-8")).decode("ascii")})
        return True, f"Schedule updated ({follow_core.ticks_per_day(cron)} wake-ups a day)."
    except AuthenticationError:
        return False, ("Schedule not updated: the token cannot change workflow files "
                       "(it needs the 'workflow' permission). It still wakes up every hour.")
    except Exception as e:
        return False, f"Schedule not updated: {str(e)[:60]}"


def start_save(follows, on_done):
    """Saves the list and syncs the schedule: ``{"ok", "schedule": message}``."""
    def work():
        payload = {"tz": follow_core.TZ_NAME, "follows": follows}
        repo_files.replace_file(CONFIG_BRANCH, FOLLOWS_FILE,
                                (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
                                "Auto follow: update the channels")
        _ok, message = sync_schedule(follows)
        return {"schedule": message}
    run_in_background(_guarded, on_done, work)


def start_sync(follows, on_done):
    def work():
        _ok, message = sync_schedule(follows)
        return {"schedule": message}
    run_in_background(_guarded, on_done, work)


def start_check_now(follow_id, on_done):
    """Starts Auto-Follow.yml now: for one channel (ignoring its time window) or
    for every enabled one. ``on_done({"ok", "run_id"})``."""
    def work():
        inputs = {"only": follow_id} if follow_id else {"force": "true"}
        return {"run_id": workflows.dispatch_and_find_run(WORKFLOW_FILE, inputs)}
    run_in_background(_guarded, on_done, work)
