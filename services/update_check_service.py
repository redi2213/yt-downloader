"""Is there a newer version on GitHub? Reads version.txt of the main branch
(build-apk.yml raises it after every successful build)."""
from api.github import client
from api.github.auth import auth_headers
from core import version_check
from core.async_utils import run_in_background
from core.config import API_BASE, APP_VERSION
from core.exceptions import AuthenticationError


def start_check(on_done):
    """``on_done({"ok", "current", "latest", "state"})`` or ``{"ok": False, "error"}``,
    called from a background thread."""
    run_in_background(_work, on_done)


def _work(on_done):
    try:
        headers = dict(auth_headers())
        headers["Accept"] = "application/vnd.github.raw+json"
        r = client.get(f"{API_BASE}/contents/version.txt", params={"ref": "main"}, headers=headers)
        latest = r.text.strip()
        on_done({"ok": True, "current": APP_VERSION, "latest": latest,
                 "state": version_check.compare(APP_VERSION, latest)})
    except AuthenticationError:
        on_done({"ok": False, "error": "GitHub token invalid or expired. Update it and retry."})
    except Exception as e:
        on_done({"ok": False, "error": f"Network error: {str(e)[:60]}"})
