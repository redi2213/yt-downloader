"""The "download history" screen is backed live by GitHub Releases rather
than local job history - these functions list, delete, rename, and zip
those releases.
"""
import uuid

from api.github import releases, workflows
from core.async_utils import run_in_background
from core.exceptions import AuthenticationError

_TOKEN_ERROR = "GitHub token invalid or expired. Update it and retry."


def start_load_live_history(on_complete=None):
    run_in_background(_load_live_history_thread, on_complete)


def _load_live_history_thread(on_complete):
    try:
        items = releases.get_live_history()
    except Exception:
        items = []
    _emit_complete(on_complete, items)


def start_delete_release(item, on_complete=None):
    run_in_background(_delete_thread, item, on_complete)


def _delete_thread(item, on_complete):
    try:
        releases.delete_release(item["release_id"], item["tag_name"])
        _emit_complete(on_complete, {"ok": True})
    except AuthenticationError:
        _emit_complete(on_complete, {"ok": False, "error": _TOKEN_ERROR})
    except Exception as e:
        _emit_complete(on_complete, {"ok": False, "error": f"Delete failed: {str(e)[:60]}"})


def start_bulk_delete_releases(items, on_status=None, on_complete=None):
    run_in_background(_bulk_delete_thread, items, on_status, on_complete)


def _bulk_delete_thread(items, on_status, on_complete):
    done = 0
    failed = 0
    for item in items:
        try:
            releases.delete_release(item["release_id"], item["tag_name"])
        except Exception:
            failed += 1
        done += 1
        _emit(on_status, f"Deleting {done}/{len(items)}...")
    from services.notify_service import notify
    notify("YT Bridge Git", f"Deleted {done - failed}/{len(items)} releases")
    _emit_complete(on_complete, {"ok": True})


def start_rename_release(item, new_name, on_complete=None):
    run_in_background(_rename_thread, item, new_name, on_complete)


def _rename_thread(item, new_name, on_complete):
    try:
        releases.rename_release_asset(item["release_id"], item["asset_id"], new_name)
        _emit_complete(on_complete, {"ok": True})
    except AuthenticationError:
        _emit_complete(on_complete, {"ok": False, "error": _TOKEN_ERROR})
    except Exception as e:
        _emit_complete(on_complete, {"ok": False, "error": f"Rename failed: {str(e)[:60]}"})


def start_zip_release(item, on_complete=None):
    run_in_background(_zip_thread, item, on_complete)


def _zip_thread(item, on_complete):
    job_id = uuid.uuid4().hex[:12]
    try:
        workflows.dispatch_workflow("zip-release.yml", {
            "asset_url": item["link"],
            "asset_name": item["title"],
            "release_id": str(item["release_id"]),
            "job_id": job_id,
        })
        run_id = workflows.get_run_id_by_job_id("zip-release.yml", job_id)
        if run_id is None:
            _emit_complete(on_complete, {
                "ok": False, "error": "Could not detect the zip workflow run. It may still be running."})
            return
        conclusion = workflows.wait_for_run(run_id)
        if conclusion != "success":
            _emit_complete(on_complete, {"ok": False, "error": f"Zip failed ({conclusion})"})
            return
        _emit_complete(on_complete, {"ok": True})
    except AuthenticationError:
        _emit_complete(on_complete, {"ok": False, "error": _TOKEN_ERROR})
    except Exception as e:
        _emit_complete(on_complete, {"ok": False, "error": f"Zip failed: {str(e)[:60]}"})


def _emit(on_status, text):
    if on_status:
        on_status(text)


def _emit_complete(on_complete, payload):
    if on_complete:
        on_complete(payload)
