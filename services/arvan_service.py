"""Arvan Cloud files: upload release files, list / delete / rename the files of the whole bucket.

Everything that touches Arvan runs in GitHub Actions (arvan-upload.yml and arvan-manage.yml, the
keys are the repository Secrets ARVAN_ACCESS_KEY / ARVAN_SECRET_KEY / ARVAN_BUCKET / ARVAN_ENDPOINT).
Independent of services/storage_service.py (the older "storage mode" feature).

The list of the bucket comes back as the asset arvan-list.json of the release ``arvan-index``;
every manage run writes it again, so a delete / rename returns the fresh list.
Callbacks may be called from a background thread (see core/async_utils.py).
"""
import json
import time
import uuid

from api.github import client, releases, workflows
from api.github.auth import auth_headers
from core.async_utils import run_in_background
from core.config import API_BASE
from core.exceptions import AuthenticationError

UPLOAD_WORKFLOW = "arvan-upload.yml"
MANAGE_WORKFLOW = "arvan-manage.yml"
INDEX_TAG = "arvan-index"
INDEX_ASSET = "arvan-list.json"
_TOKEN_ERROR = "GitHub token invalid or expired. Update it and retry."
_SECRETS_HINT = "Check that the ARVAN_* secrets are set in the repository."


def read_index():
    """The last list of the bucket written by arvan-manage.yml, or None when there is none yet."""
    r = client.get_allow_missing(f"{API_BASE}/releases/tags/{INDEX_TAG}")
    if r.status_code != 200:
        return None
    for asset in r.json().get("assets", []):
        if asset.get("name") == INDEX_ASSET:
            headers = dict(auth_headers())
            headers["Accept"] = "application/octet-stream"
            resp = client.get(asset["url"], headers=headers)
            data = json.loads(resp.content.decode("utf-8"))
            return data if isinstance(data, dict) else None
    return None


# ------------------------------------------------------------ list / delete / rename
def start_open(on_status=None, on_complete=None):
    """The saved list at once; when there is none yet, a fresh one from the workflow."""
    run_in_background(_open_thread, on_status, on_complete)


def start_background_refresh(on_complete=None):
    """Once when the app opens: the saved list at once, then a fresh one from the workflow - both
    reported through ``on_complete``. Does nothing when Arvan was never used (no saved list)."""
    run_in_background(_background_thread, on_complete)


def _background_thread(on_complete):
    try:
        data = read_index()
    except Exception:
        return
    if not data:
        return
    _emit(on_complete, {"ok": True, "data": data, "cached": True})
    _manage_thread("list", {}, None, on_complete)


def start_refresh(on_status=None, on_complete=None):
    run_in_background(_manage_thread, "list", {}, on_status, on_complete)


def start_delete(keys, on_status=None, on_complete=None):
    run_in_background(_manage_thread, "delete", {"keys": json.dumps(list(keys), ensure_ascii=False)},
                      on_status, on_complete)


def start_rename(old_key, new_key, on_status=None, on_complete=None):
    run_in_background(_manage_thread, "rename", {"old_key": old_key, "new_key": new_key},
                      on_status, on_complete)


def _open_thread(on_status, on_complete):
    try:
        data = read_index()
    except AuthenticationError:
        _emit(on_complete, {"ok": False, "error": _TOKEN_ERROR})
        return
    except Exception:
        data = None
    if data:
        _emit(on_complete, {"ok": True, "data": data, "cached": True})
        return
    _manage_thread("list", {}, on_status, on_complete)


def _manage_thread(action, extra, on_status, on_complete):
    job_id = uuid.uuid4().hex[:12]
    try:
        _emit(on_status, "Starting workflow...")
        inputs = {"action": action, "job_id": job_id, **extra}
        run_id = workflows.dispatch_and_find_run(MANAGE_WORKFLOW, inputs, attempts=30, delay=2)
        if run_id is None:
            _emit(on_complete, {"ok": False, "error": "Could not detect the workflow run. Try again."})
            return
        conclusion = workflows.wait_for_run(run_id, on_status=lambda s: _emit(on_status, f"{s}..."))
        data = None
        for _ in range(6):
            data = read_index()
            if data and data.get("job_id") == job_id:
                break
            data = None
            time.sleep(2)
        if data is None:
            _emit(on_complete, {"ok": False, "error": f"Arvan {action} failed ({conclusion}). {_SECRETS_HINT}"})
            return
        _emit(on_complete, {"ok": True, "data": data, "action": action})
    except AuthenticationError:
        _emit(on_complete, {"ok": False, "error": _TOKEN_ERROR})
    except Exception as e:
        _emit(on_complete, {"ok": False, "error": f"Error: {str(e)[:70]}"})


def action_summary(data, action):
    """One short text about what the last manage run did (empty after a plain list)."""
    last = (data or {}).get("last_action") or {}
    ok, failed = last.get("ok") or [], last.get("failed") or []
    if action == "delete":
        text = f"Deleted {len(ok)} file(s)."
    elif action == "rename":
        text = "Renamed." if ok else "Rename failed."
    else:
        return ""
    for f in failed[:3]:
        text += f"\n{f.get('name')}: {f.get('error')}"
    return text


# ------------------------------------------------------------ upload release files
def start_upload(items, on_status=None, on_complete=None):
    """Uploads the given Release History items (files kept on GitHub) to Arvan.
    ``on_complete({"ok", "files": [{name, url, size}], "warn": [text], "error"})``."""
    run_in_background(_upload_thread, items, on_status, on_complete)


def _upload_thread(items, on_status, on_complete):
    try:
        payload = [{"asset_id": int(it["asset_id"]), "name": it["title"]}
                   for it in items if it.get("asset_id") is not None]
        if not payload:
            _emit(on_complete, {"ok": False, "error": "Only files kept on GitHub can be uploaded to Arvan."})
            return
        _emit(on_status, "Starting workflow...")
        inputs = {"items": json.dumps(payload, ensure_ascii=False), "job_id": uuid.uuid4().hex[:12],
                  "run_title": "Arvan upload"}
        run_id = workflows.dispatch_and_find_run(UPLOAD_WORKFLOW, inputs, attempts=40, delay=3)
        if run_id is None:
            _emit(on_complete, {"ok": False, "error": "Could not detect the workflow run. It may still be starting."})
            return
        conclusion = workflows.wait_for_run(run_id, on_status=lambda s: _emit(on_status, f"{s}..."))
        body = releases.get_release_body(run_id, attempts=5, delay=2) or ""
        meta = releases.parse_storage_meta(body) or {}
        files = [f for f in meta.get("files", []) if isinstance(f, dict) and f.get("url")]
        warn = [str(w) for w in meta.get("warn", [])]
        if not files:
            why = "; ".join(warn) or f"upload {conclusion}. {_SECRETS_HINT}"
            _emit(on_complete, {"ok": False, "error": f"Nothing was uploaded: {why}"[:300]})
            return
        _emit(on_complete, {"ok": True, "files": files, "warn": warn, "run_id": run_id})
    except AuthenticationError:
        _emit(on_complete, {"ok": False, "error": _TOKEN_ERROR})
    except Exception as e:
        _emit(on_complete, {"ok": False, "error": f"Error: {str(e)[:70]}"})


def _emit(callback, value):
    if callback:
        callback(value)
