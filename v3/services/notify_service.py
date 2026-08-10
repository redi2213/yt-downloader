"""Best-effort OS notifications (via plyer). Not GitHub-specific, so this
lives in the services layer rather than the api layer.
"""
try:
    from plyer import notification
    HAS_NOTIFY = True
except Exception:
    HAS_NOTIFY = False


def notify(title: str, message: str) -> None:
    if HAS_NOTIFY:
        try:
            notification.notify(title=title, message=message, timeout=5)
        except Exception:
            pass
