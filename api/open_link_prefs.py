"""Where the "Open on GitHub" buttons open the link, kept on this phone:
  ""     ask every time (default)
  app    the official GitHub app
  chrome Chrome / the default browser (never the GitHub app)
  inapp  the app's own browser (screens/browser.py)
"""
from api.github.auth import _settings_store

_KEY = "open_link"
CHOICES = ("app", "chrome", "inapp")
OPTIONS = [("app", "GitHub app"), ("chrome", "Google Chrome / browser"), ("inapp", "This app's browser")]
LABELS = {"": "Ask every time", "app": "GitHub app", "chrome": "Chrome / browser", "inapp": "This app's browser"}


def get_choice() -> str:
    """The remembered choice, or "" when the app should ask."""
    try:
        if _settings_store.exists(_KEY):
            value = str(dict(_settings_store.get(_KEY)).get("choice") or "")
            return value if value in CHOICES else ""
    except Exception:
        pass
    return ""


def set_choice(choice) -> None:
    _settings_store.put(_KEY, choice=choice if choice in CHOICES else "")


def next_choice(current=None) -> str:
    order = ("",) + CHOICES
    current = get_choice() if current is None else current
    return order[(order.index(current) + 1) % len(order)] if current in order else ""


def label(choice=None) -> str:
    return LABELS.get(get_choice() if choice is None else choice, LABELS[""])
