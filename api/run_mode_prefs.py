"""Where the "finding out" steps run: on GitHub, on the phone itself, or auto.

  github  the way it always was (a workflow does it)
  phone   this phone's own internet, like a Termux script (fast, no runner start)
  auto    the phone first; when it fails the same step runs on GitHub (default)

Kept in the same on-device store as the other settings (see storage_prefs.py).
Only steps that can work on the phone look at it: the YouTube playlist video
list and the YouTube quality list. Downloading the file itself stays on GitHub.
"""
from api.github.auth import _settings_store

MODES = ("auto", "github", "phone")
MODE_LABELS = {"auto": "Auto (phone first)", "github": "GitHub", "phone": "Phone"}
_KEY = "run_mode"


def get_mode() -> str:
    if _settings_store.exists(_KEY):
        mode = dict(_settings_store.get(_KEY)).get("mode", "auto")
        return mode if mode in MODES else "auto"
    return "auto"


def set_mode(mode: str) -> None:
    _settings_store.put(_KEY, mode=mode if mode in MODES else "auto")


def next_mode(current: str = None) -> str:
    current = current or get_mode()
    return MODES[(MODES.index(current) + 1) % len(MODES)] if current in MODES else "auto"


def label(mode: str = None) -> str:
    return MODE_LABELS.get(mode or get_mode(), MODE_LABELS["auto"])


def other_side(mode: str = None) -> str:
    """The side the per-tool exception button offers: ``phone`` unless the
    default already is the phone."""
    return "github" if (mode or get_mode()) == "phone" else "phone"
