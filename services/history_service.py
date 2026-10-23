"""The "download history" screen is backed live by GitHub Releases rather
than local job history - these functions list, delete, rename, and zip
those releases.
"""
import uuid

from api.github import client, releases, workflows
from core.async_utils import run_in_background
from core.config import BOT_API_BASE, BOT_DEFAULT_BRANCH, BOT_WORKER_URL
from core.exceptions import AuthenticationError

_TOKEN_ERROR = "GitHub token invalid or expired. Update it and retry."


def start_load_live_history(on_complete=None, tag=None, page=0, repo=None):
    """``on_complete({"items", "has_next", "page"})``. With ``tag`` (one Auto
    follow channel) the whole release is returned as a single page. ``repo="bot"``:
    the Telegram bot's releases (aparat-bot); a failure then comes back as ``error``."""
    run_in_background(_load_live_history_thread, on_complete, tag, page, repo)


_BOT_NO_ACCESS = ("No access to the Telegram bot repo (aparat-bot). "
                  "Install the YT Bridge Auth app on it (Contents + Actions).")


def _bot_error(e):
    status = getattr(getattr(e, "response", None), "status_code", None)
    if isinstance(e, AuthenticationError) or status in (401, 403, 404):
        return _BOT_NO_ACCESS
    return f"Could not load the bot files: {str(e)[:60]}"


def _sign_bot_links(items):
    """Replace the plain GitHub link of each bot file with a signed Worker link (the repo is
    private, so GitHub's own link gives 404 without a login). On any failure the items keep
    their GitHub link."""
    todo = [it for it in items if it.get("asset_id") and it.get("tag_name") and it.get("title")]
    if not todo:
        return
    try:
        r = client.post(f"{BOT_WORKER_URL}/app/sign",
                        json={"items": [{"tag": it["tag_name"], "name": it["title"]} for it in todo]})
        links = r.json().get("links") or []
    except Exception:
        return
    if len(links) != len(todo):
        return
    for it, link in zip(todo, links):
        it["link"] = link


def _load_live_history_thread(on_complete, tag=None, page=0, repo=None):
    error = None
    try:
        if tag:
            items, has_next, page = releases.get_live_history(tag), False, 0
        else:
            items, has_next, page = releases.get_live_history_page(page, repo=repo)
            if repo == "bot":
                _sign_bot_links(items)
    except Exception as e:
        items, has_next, page = [], False, 0
        if repo == "bot":
            error = _bot_error(e)
    _emit_complete(on_complete, {"items": items, "has_next": has_next, "page": page, "error": error})


def start_delete_release(item, on_complete=None):
    run_in_background(_delete_thread, item, on_complete)


def _delete_thread(item, on_complete):
    try:
        releases.delete_history_item(item)
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
            releases.delete_history_item(item)
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
        releases.rename_release_asset(item["release_id"], item["asset_id"], new_name, item.get("repo"))
        _emit_complete(on_complete, {"ok": True})
    except AuthenticationError:
        _emit_complete(on_complete, {"ok": False, "error": _TOKEN_ERROR})
    except Exception as e:
        _emit_complete(on_complete, {"ok": False, "error": f"Rename failed: {str(e)[:60]}"})


def start_zip_release(item, on_complete=None):
    run_in_background(_zip_thread, item, on_complete)


def _zip_thread(item, on_complete):
    job_id = uuid.uuid4().hex[:12]
    # a Telegram bot file is zipped by the zip-release.yml of the bot's own repo
    base = BOT_API_BASE if item.get("repo") == "bot" else None
    ref = BOT_DEFAULT_BRANCH if base else None
    try:
        workflows.dispatch_workflow("zip-release.yml", {
            "asset_url": item["link"],
            "asset_name": item["title"],
            "release_id": str(item["release_id"]),
            "job_id": job_id,
        }, api_base=base, ref=ref)
        run_id = workflows.get_run_id_by_job_id("zip-release.yml", job_id, api_base=base)
        if run_id is None:
            _emit_complete(on_complete, {
                "ok": False, "error": "Could not detect the zip workflow run. It may still be running."})
            return
        conclusion = workflows.wait_for_run(run_id, api_base=base)
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
