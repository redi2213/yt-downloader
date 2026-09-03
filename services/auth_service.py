"""GitHub Device Flow sign-in, run in the background so the UI can show a
'waiting for approval...' screen with the user_code while polling.

Same shape as the rest of services/: on_status reports the code/status to
show, on_complete reports final success/failure. The access_token, once
obtained, is saved through token_service - the same storage every other
part of the app already reads from, so nothing else needs to change to
start using a device-flow-obtained token instead of a manually pasted one.
"""
import time

from api.github import device_auth
from core.async_utils import run_in_background
from services import token_service


def start_device_flow(on_status=None, on_complete=None):
    """on_status receives a dict describing what to show the user:
      {"stage": "code", "user_code": ..., "verification_uri": ...}
      {"stage": "waiting"}
    on_complete receives {"ok": bool, "error": str (if not ok)}."""
    run_in_background(_device_flow_thread, on_status, on_complete)


def _device_flow_thread(on_status, on_complete):
    try:
        info = device_auth.request_device_code()
    except Exception as e:
        _emit_complete(on_complete, {"ok": False, "error": f"Could not start sign-in: {str(e)[:60]}"})
        return

    device_code = info["device_code"]
    user_code = info["user_code"]
    verification_uri = info["verification_uri"]
    interval = info.get("interval", 5)
    expires_in = info.get("expires_in", 900)

    _emit(on_status, {
        "stage": "code",
        "user_code": user_code,
        "verification_uri": verification_uri,
    })

    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        try:
            access_token = device_auth.poll_once(device_code)
        except device_auth.AuthPending:
            continue
        except device_auth.AuthSlowDown:
            interval += 5
            continue
        except device_auth.AuthExpired:
            _emit_complete(on_complete, {"ok": False, "error": "Code expired. Try again."})
            return
        except device_auth.AuthDenied:
            _emit_complete(on_complete, {"ok": False, "error": "Sign-in was denied."})
            return
        except Exception as e:
            _emit_complete(on_complete, {"ok": False, "error": f"Network error: {str(e)[:60]}"})
            return

        token_service.save_token(access_token)
        _emit_complete(on_complete, {"ok": True})
        return

    _emit_complete(on_complete, {"ok": False, "error": "Code expired. Try again."})


def _emit(on_status, payload):
    if on_status:
        on_status(payload)


def _emit_complete(on_complete, payload):
    if on_complete:
        on_complete(payload)
