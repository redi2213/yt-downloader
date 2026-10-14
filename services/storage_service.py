"""Arvan Cloud storage settings and information.

Everything that touches Arvan itself happens in GitHub Actions (the keys are
repository Secrets the app cannot read back):

* adding / removing a bucket writes or deletes its Secrets (Settings > Storage)
* the usage screen and "delete expired files" run the arvan-maintenance.yml
  workflow and read its result from the description of release run-<id>

Callbacks may be called from a background thread (see core/async_utils.py).
"""
from api import storage_prefs
from api.github import releases, secrets, workflows
from core import storage_format as fmt
from core.async_utils import run_in_background
from core.exceptions import AuthenticationError

MAINTENANCE_WORKFLOW = "arvan-maintenance.yml"
_SECRET_SUFFIXES = ("ACCESS_KEY", "SECRET_KEY", "BUCKET", "ENDPOINT", "QUOTA_GB")

SECRETS_HELP = ("The GitHub token cannot write Secrets. Allow \"Secrets: Read and write\" "
                "for the app (or use a token with the repo scope) and sign in again.")


# ------------------------------------------------------------------ mode ---
def get_mode() -> str:
    return storage_prefs.get_mode()


def set_mode(mode: str) -> None:
    storage_prefs.set_mode(mode)


def cycle_mode() -> str:
    mode = storage_prefs.next_mode()
    storage_prefs.set_mode(mode)
    return mode


def mode_label(mode: str = None) -> str:
    return storage_prefs.MODE_LABELS.get(mode or storage_prefs.get_mode(), "GitHub")


# --------------------------------------------------------------- buckets ---
def start_load_buckets(on_complete=None):
    run_in_background(_load_buckets_thread, on_complete)


def _load_buckets_thread(on_complete):
    try:
        ids = fmt.bucket_ids(secrets.list_secret_names())
        labels = storage_prefs.get_labels()
        active = storage_prefs.get_bucket() or (ids[0] if ids else "")
        buckets = [{"id": i, "label": labels.get(i) or f"bucket {i}", "active": i == active}
                   for i in ids]
        _emit(on_complete, {"ok": True, "buckets": buckets})
    except AuthenticationError:
        _emit(on_complete, {"ok": False, "error": SECRETS_HELP})
    except Exception as e:
        _emit(on_complete, {"ok": False, "error": f"Could not read the buckets: {str(e)[:70]}"})


def set_active_bucket(bucket_id: str) -> None:
    storage_prefs.set_bucket(bucket_id)


def start_add_bucket(access_key, secret_key, bucket, endpoint="", quota_gb="", on_complete=None):
    run_in_background(_add_bucket_thread, access_key, secret_key, bucket, endpoint, quota_gb, on_complete)


def _add_bucket_thread(access_key, secret_key, bucket, endpoint, quota_gb, on_complete):
    access_key, secret_key, bucket = (access_key or "").strip(), (secret_key or "").strip(), (bucket or "").strip()
    if not (access_key and secret_key and bucket):
        _emit(on_complete, {"ok": False, "error": "Access key, secret key and bucket name are all needed."})
        return
    endpoint = (endpoint or "").strip().rstrip("/") or fmt.DEFAULT_ENDPOINT
    if not endpoint.startswith("https://"):
        _emit(on_complete, {"ok": False, "error": "The endpoint must start with https://"})
        return
    quota = fmt.parse_quota(quota_gb)
    try:
        existing = fmt.bucket_ids(secrets.list_secret_names())
        bucket_id = fmt.next_bucket_id(existing)
        prefix = fmt.secret_prefix(bucket_id)
        values = {"ACCESS_KEY": access_key, "SECRET_KEY": secret_key, "BUCKET": bucket,
                  "ENDPOINT": endpoint, "QUOTA_GB": f"{quota:g}"}
        for suffix, value in values.items():
            secrets.put_secret(f"{prefix}_{suffix}", value)
        storage_prefs.set_label(bucket_id, bucket)
        if not storage_prefs.get_bucket():
            storage_prefs.set_bucket(bucket_id)
        _emit(on_complete, {"ok": True, "id": bucket_id, "bucket": bucket})
    except AuthenticationError:
        _emit(on_complete, {"ok": False, "error": SECRETS_HELP})
    except Exception as e:
        _emit(on_complete, {"ok": False, "error": f"Could not save the bucket: {str(e)[:70]}"})


def start_remove_bucket(bucket_id, on_complete=None):
    run_in_background(_remove_bucket_thread, bucket_id, on_complete)


def _remove_bucket_thread(bucket_id, on_complete):
    try:
        prefix = fmt.secret_prefix(bucket_id)
        for suffix in _SECRET_SUFFIXES:
            secrets.delete_secret(f"{prefix}_{suffix}")
        storage_prefs.remove_label(bucket_id)
        _emit(on_complete, {"ok": True})
    except AuthenticationError:
        _emit(on_complete, {"ok": False, "error": SECRETS_HELP})
    except Exception as e:
        _emit(on_complete, {"ok": False, "error": f"Could not remove the bucket: {str(e)[:70]}"})


# ----------------------------------------------- usage info and cleanup ---
def start_arvan_info(on_status=None, on_complete=None):
    run_in_background(_maintenance_thread, "info", on_status, on_complete)


def start_arvan_cleanup(on_status=None, on_complete=None):
    run_in_background(_maintenance_thread, "cleanup", on_status, on_complete)


def _maintenance_thread(action, on_status, on_complete):
    try:
        _emit(on_status, "Starting workflow...")
        run_id = workflows.dispatch_and_find_run(MAINTENANCE_WORKFLOW, {"action": action})
        if run_id is None:
            _emit(on_complete, {"ok": False, "error": "Could not detect the workflow run. Try again."})
            return
        conclusion = workflows.wait_for_run(run_id, on_status=(lambda s: _emit(on_status, f"{s}...")))
        if conclusion != "success":
            _emit(on_complete, {"ok": False, "error": f"Arvan {action} failed ({conclusion}). "
                                                    "Check that the ARVAN_* secrets are set."})
            return
        data = releases.parse_arvan_info(releases.get_release_body(run_id))
        if not data:
            _emit(on_complete, {"ok": False, "error": "The workflow finished but left no result."})
            return
        _emit(on_complete, {"ok": True, "action": action, "data": data})
    except AuthenticationError:
        _emit(on_complete, {"ok": False, "error": "GitHub token invalid or expired. Update it and retry."})
    except Exception as e:
        _emit(on_complete, {"ok": False, "error": f"Error: {str(e)[:70]}"})


def cleanup_summary(data: dict) -> str:
    """One line per bucket: how many files were deleted and the space freed."""
    lines = []
    for b in data.get("buckets", []):
        name = b.get("bucket") or b.get("id")
        if b.get("error"):
            lines.append(f"{name}: failed ({b['error']})")
        else:
            lines.append(f"{name}: deleted {b.get('deleted', 0)} file(s), freed {fmt.fmt_bytes(b.get('freed_bytes', 0))}")
    return "\n".join(lines) or "No Arvan bucket is configured."


def _emit(callback, value):
    if callback:
        callback(value)
