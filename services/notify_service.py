"""Best-effort OS notifications. On Android they are built by core/android_notify.py so that
tapping one can open the right screen; plyer is the fallback (desktop, or if that fails).
Not GitHub-specific, so this lives in the services layer rather than the api layer.
"""
try:
    from plyer import notification
    HAS_NOTIFY = True
except Exception:
    HAS_NOTIFY = False


def notify(title: str, message: str, job_id=None, run_id=None) -> None:
    """``job_id`` / ``run_id``: tapping the notification opens that job's (or run's) result."""
    try:
        from core import android_notify
        if android_notify.show(title, message, job_id=job_id, run_id=run_id):
            return
    except Exception:
        pass
    if HAS_NOTIFY:
        try:
            notification.notify(title=title, message=message, timeout=5)
        except Exception:
            pass
