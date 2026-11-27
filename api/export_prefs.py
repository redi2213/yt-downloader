"""Full page export (in-app browser > Export cookies > Full page export): the private repository the files go to and
the token that may write to it, kept on this phone.

The token is a fine-grained GitHub token for that one repository only (Contents: read and write). It is typed in
Settings > Account and sign-in and is never in the code. The public repository (yt-downloader) never gets any of
the exported data.
"""
from api.github.auth import _settings_store

_KEY = "exports"
REPO = "redi2213/yt-exports"
BRANCH = "main"


def get_token() -> str:
    try:
        if _settings_store.exists(_KEY):
            return str(dict(_settings_store.get(_KEY)).get("token") or "")
    except Exception:
        pass
    return ""


def set_token(token) -> None:
    _settings_store.put(_KEY, token=str(token or "").strip())
