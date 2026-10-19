"""The ntfy topic kept on this phone (the app shows it in Settings and uses it
to send a test message). The copy the workflows read lives on the ``config``
branch (``ntfy.json``) - see services/ntfy_service.py.
"""
from api.github.auth import _settings_store

_KEY = "ntfy"
DEFAULT_SERVER = "https://ntfy.sh"


def get_topic() -> str:
    if _settings_store.exists(_KEY):
        return str(dict(_settings_store.get(_KEY)).get("topic", ""))
    return ""


def set_topic(topic: str) -> None:
    _settings_store.put(_KEY, topic=topic)
