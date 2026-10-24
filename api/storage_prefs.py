"""Where finished files are kept: GitHub Release, Arvan Cloud, or both.

Two small settings kept in the same on-device store as the tokens (a second
JsonStore on the same file would overwrite the first one's keys, so the
existing store object is reused - same note as in filimo.py):

  mode    "github" | "arvan" | "both"   (default "github")
  bucket  id of the preferred Arvan bucket ("main", "2", ...; "" = main)
"""
from api.github.auth import _settings_store

MODES = ("github", "arvan", "both")
MODE_LABELS = {"github": "GitHub", "arvan": "Arvan", "both": "GitHub + Arvan"}
_KEY = "storage"


def _read() -> dict:
    if _settings_store.exists(_KEY):
        return dict(_settings_store.get(_KEY))
    return {}


def get_mode() -> str:
    """Arvan Cloud is switched off for now: every file stays on GitHub, whatever an older
    version of the app saved. To bring it back, restore the lines below (git history)."""
    return "github"
    # mode = _read().get("mode", "github")
    # return mode if mode in MODES else "github"


def set_mode(mode: str) -> None:
    if mode not in MODES:
        mode = "github"
    data = _read()
    data["mode"] = mode
    _settings_store.put(_KEY, **data)


def next_mode(current: str = None) -> str:
    """The mode after ``current`` in the github -> arvan -> both cycle."""
    current = current or get_mode()
    return MODES[(MODES.index(current) + 1) % len(MODES)] if current in MODES else "github"


def get_bucket() -> str:
    return ""   # Arvan is switched off (see get_mode); was: _read().get("bucket", "") or ""


def set_bucket(bucket_id: str) -> None:
    data = _read()
    data["bucket"] = bucket_id or ""
    _settings_store.put(_KEY, **data)


def get_labels() -> dict:
    """bucket id -> the bucket name the user typed when adding it (secret
    values cannot be read back, so the app remembers the name itself)."""
    labels = _read().get("labels", {})
    return dict(labels) if isinstance(labels, dict) else {}


def set_label(bucket_id: str, label: str) -> None:
    data = _read()
    labels = data.get("labels", {})
    labels = dict(labels) if isinstance(labels, dict) else {}
    labels[bucket_id] = label
    data["labels"] = labels
    _settings_store.put(_KEY, **data)


def remove_label(bucket_id: str) -> None:
    data = _read()
    labels = data.get("labels", {})
    labels = dict(labels) if isinstance(labels, dict) else {}
    labels.pop(bucket_id, None)
    data["labels"] = labels
    if data.get("bucket") == bucket_id:
        data["bucket"] = ""
    _settings_store.put(_KEY, **data)
