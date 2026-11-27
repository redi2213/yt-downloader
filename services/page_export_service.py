"""Full page export: uploads the files to the private repository (api/export_prefs.REPO) with the GitHub Contents API
(PUT /repos/<repo>/contents/<path>). Uses the export token only (never the app's main token). Blocking work runs in
a background thread; no Kivy here. The token never goes into an error text.
"""
import base64
from urllib.parse import quote

from api import export_prefs
from api.github import client
from core.async_utils import run_in_background
from core.exceptions import AuthenticationError

_API = "https://api.github.com"


def _headers(token):
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def start_upload(folder, files, on_progress, on_complete):
    """on_progress(text) while uploading; on_complete({'ok': True, 'path': folder, 'files': [...]}) or
    {'ok': False, 'error': str}."""
    run_in_background(_upload_thread, folder, files, on_progress, on_complete)


def _error_text(e, done):
    status = getattr(getattr(e, "response", None), "status_code", None)
    if isinstance(e, AuthenticationError) or status in (401, 403):
        return "Exports token is invalid, expired or has no write access to " + export_prefs.REPO + "."
    if status == 404:
        return export_prefs.REPO + " was not found, or the exports token has no access to it."
    if status == 422:
        return "This export already exists in the repository."
    return f"Error after {len(done)} file(s): " + str(e)[:80]


def _upload_thread(folder, files, on_progress, on_complete):
    token = export_prefs.get_token()
    if not token:
        on_complete({"ok": False, "error": "No exports token: add it in Settings > Account and sign-in."})
        return
    done = []
    try:
        total = len(files)
        for number, (name, content) in enumerate(files.items(), 1):
            on_progress(f"Uploading {number}/{total}: {name}")
            body = {"message": f"export {folder}",
                    "content": base64.b64encode(str(content).encode("utf-8")).decode("ascii"),
                    "branch": export_prefs.BRANCH}
            url = f"{_API}/repos/{export_prefs.REPO}/contents/{quote(folder + '/' + name)}"
            client.request("PUT", url, json=body, headers=_headers(token))
            done.append(name)
        on_complete({"ok": True, "path": folder, "files": done})
    except Exception as e:
        on_complete({"ok": False, "error": _error_text(e, done)})
