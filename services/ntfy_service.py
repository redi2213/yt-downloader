"""Push notifications through ntfy when the app is closed.

The last step of every workflow sends a short message (OK / FAILED, the tool,
the run link) to the topic written in ``ntfy.json`` on the ``config`` branch.
The topic is typed ONCE in the app (Settings); saving it commits that file, so
nothing has to be given to each workflow. The topic works like a password
(anyone who knows it can read the messages), so the app can make a long random one.

ntfy.json: {"topic": "ytb-...", "server": "https://ntfy.sh"}  (server optional)
"""
import json
import re
import uuid

import requests

from api import ntfy_prefs
from api.github import client, repo_files
from api.github.auth import auth_headers
from core.async_utils import run_in_background
from core.config import API_BASE
from core.exceptions import AuthenticationError

CONFIG_BRANCH = "config"
FILE_NAME = "ntfy.json"
_TOPIC_RE = re.compile(r"[A-Za-z0-9_-]{6,64}")


def generate_topic() -> str:
    return "ytb-" + uuid.uuid4().hex[:16]


def valid_topic(topic: str) -> bool:
    return bool(_TOPIC_RE.fullmatch(topic or ""))


def _server_from(config) -> str:
    server = str((config or {}).get("server") or ntfy_prefs.DEFAULT_SERVER).strip().rstrip("/")
    return server if re.fullmatch(r"https://[A-Za-z0-9.\-]+(:[0-9]+)?", server) else ntfy_prefs.DEFAULT_SERVER


def _read_remote() -> dict:
    headers = dict(auth_headers())
    headers["Accept"] = "application/vnd.github.raw+json"
    r = client.get_allow_missing(f"{API_BASE}/contents/{FILE_NAME}",
                                 params={"ref": CONFIG_BRANCH}, headers=headers)
    if r.status_code != 200:
        return {}
    try:
        data = json.loads(r.text)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _error_text(e) -> str:
    if isinstance(e, AuthenticationError):
        return "GitHub token invalid, expired or not allowed to write to the config branch."
    return f"Error: {str(e)[:80]}"


def _guarded(on_done, work):
    try:
        on_done({"ok": True, **work()})
    except ValueError as e:
        on_done({"ok": False, "error": str(e)})
    except Exception as e:
        on_done({"ok": False, "error": _error_text(e)})


def start_load(on_done):
    """The topic the workflows use now (read from the config branch)."""
    def work():
        topic = str(_read_remote().get("topic") or "")
        if topic:
            ntfy_prefs.set_topic(topic)
        return {"topic": topic}
    run_in_background(_guarded, on_done, work)


def start_save(topic, on_done):
    """Writes ``ntfy.json`` on the config branch (an empty topic turns the
    notifications off for every workflow)."""
    topic = (topic or "").strip()

    def work():
        if topic and not valid_topic(topic):
            raise ValueError("The topic needs 6-64 letters, digits, - or _ (no spaces).")
        current = _read_remote()
        data = {"topic": topic, "server": _server_from(current)}
        repo_files.replace_file(CONFIG_BRANCH, FILE_NAME,
                                (json.dumps(data, indent=2) + "\n").encode("utf-8"),
                                "Set ntfy topic" if topic else "Turn ntfy off")
        ntfy_prefs.set_topic(topic)
        return {"topic": topic}
    run_in_background(_guarded, on_done, work)


def start_test(topic, on_done):
    """Sends a test message from the phone (shows if the topic works)."""
    topic = (topic or "").strip()

    def work():
        if not valid_topic(topic):
            raise ValueError("Type or generate a topic first.")
        server = _server_from(_read_remote())
        r = requests.post(f"{server}/{topic}", data="Test from YT Bridge".encode("utf-8"),
                          headers={"Title": "YT Bridge test", "Tags": "bell"}, timeout=15)
        r.raise_for_status()
        return {}
    run_in_background(_guarded, on_done, work)
