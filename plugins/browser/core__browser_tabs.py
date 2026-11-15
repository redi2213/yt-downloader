"""In-app browser: open tabs, history and bookmarks (pure Python: no Kivy, no network, no Build).

One native WebView shows the active tab. Every other tab is only a small record (id, address, title) plus a
``Session`` (the files found in that tab), made the first time the tab is opened - so many tabs cost little memory.
A tab left in the background keeps only its newest files (``Session.trim``); the lists are capped.
"""
import time

from core.browser_media import Session

MAX_TABS = 20
MAX_HISTORY = 500
MAX_BOOKMARKS = 500
KEEP_ITEMS = 300            # files a background tab keeps
_MAX_URL = 600
_MAX_TITLE = 120


def is_web(url):
    return str(url or "").lower().startswith(("http://", "https://"))


def _clip(text, size):
    return " ".join(str(text or "").split())[:size]


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def short_url(url, size=70):
    """An address for a list row: no scheme, no www., no closing slash, cut to ``size``."""
    text = str(url or "")
    for prefix in ("https://", "http://"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    if text.lower().startswith("www."):
        text = text[4:]
    text = text.rstrip("/")
    return text if len(text) <= size else text[:size - 3] + "..."


def when(ts, now=None):
    """\"14:05\" for today, \"2026-11-02 14:05\" for an older day."""
    try:
        t = time.localtime(float(ts))
        n = time.localtime(time.time() if now is None else now)
    except (TypeError, ValueError, OverflowError, OSError):
        return ""
    if (t.tm_year, t.tm_yday) == (n.tm_year, n.tm_yday):
        return time.strftime("%H:%M", t)
    return time.strftime("%Y-%m-%d %H:%M", t)


class Tabs:
    """The open tabs: [{id, url, title}], which one is active, and the Session of each opened tab."""

    def __init__(self, tabs=None, active=None):
        self.tabs = []
        self.sessions = {}
        self.dirty = False
        seen = set()
        for t in tabs or []:
            if len(self.tabs) >= MAX_TABS:
                break
            if not isinstance(t, dict) or not t.get("id") or str(t["id"]) in seen:
                continue
            seen.add(str(t["id"]))
            url = _clip(t.get("url"), _MAX_URL)
            tab = {"id": str(t["id"]), "url": url if is_web(url) else "", "title": _clip(t.get("title"), _MAX_TITLE)}
            if t.get("desktop"):
                tab["desktop"] = True       # the tab shows the desktop version of sites
            self.tabs.append(tab)
        if not self.tabs:
            self.tabs.append(self._blank())
        ids = [t["id"] for t in self.tabs]
        self.active = active if active in ids else ids[0]

    @classmethod
    def from_data(cls, data):
        data = data if isinstance(data, dict) else {}
        tabs = data.get("tabs")
        return cls(tabs if isinstance(tabs, list) else [], data.get("active"))

    def to_data(self):
        return {"active": self.active, "tabs": [dict(t) for t in self.tabs]}

    def _new_id(self):
        used = {t["id"] for t in self.tabs}
        n = int(time.time() * 1000)
        while f"t{n}" in used:
            n += 1
        return f"t{n}"

    def _blank(self, url=""):
        return {"id": self._new_id(), "url": url if is_web(url) else "", "title": ""}

    def find(self, tab_id):
        return next((t for t in self.tabs if t["id"] == tab_id), None)

    def current(self):
        return self.find(self.active)

    def is_desktop(self, tab_id):
        tab = self.find(tab_id)
        return bool(tab and tab.get("desktop"))

    def set_desktop(self, tab_id, on):
        """Desktop view of one tab (kept with the tab, so it stays after the app is closed)."""
        tab = self.find(tab_id)
        if tab is None:
            return False
        if bool(tab.get("desktop")) != bool(on):
            if on:
                tab["desktop"] = True
            else:
                tab.pop("desktop", None)
            self.dirty = True
        return True

    def count(self):
        return len(self.tabs)

    def full(self):
        return len(self.tabs) >= MAX_TABS

    def new(self, url=""):
        """A new tab (it becomes the active one); None when MAX_TABS are open."""
        if self.full():
            return None
        tab = self._blank(url)
        self.tabs.append(tab)
        self.activate(tab["id"])
        self.dirty = True
        return tab

    def activate(self, tab_id):
        if self.find(tab_id) is None:
            return False
        if tab_id != self.active:
            old = self.sessions.get(self.active)
            if old is not None:
                old.trim(KEEP_ITEMS)        # the tab we leave keeps only its newest files
            self.active = tab_id
            self.dirty = True
        return True

    def close(self, tab_id):
        """Closes one tab; returns the tab that is active afterwards (a blank one when none was left)."""
        i = next((n for n, t in enumerate(self.tabs) if t["id"] == tab_id), -1)
        if i < 0:
            return self.current()
        self.tabs.pop(i)
        self.sessions.pop(tab_id, None)
        self.dirty = True
        if not self.tabs:
            self.tabs.append(self._blank())
        if tab_id == self.active:
            self.active = self.tabs[min(i, len(self.tabs) - 1)]["id"]
        return self.current()

    def close_all(self):
        self.tabs, self.sessions = [], {}
        tab = self._blank()
        self.tabs.append(tab)
        self.active = tab["id"]
        self.dirty = True
        return tab

    def session_for(self, tab_id):
        s = self.sessions.get(tab_id)
        if s is None:
            s = self.sessions[tab_id] = Session()
        return s

    def update(self, tab_id, url, title=""):
        """The address and title the page of a tab reports. Returns (address_changed, title_changed)."""
        tab = self.find(tab_id)
        url = _clip(url, _MAX_URL)
        if tab is None or not is_web(url):
            return False, False
        title = _clip(title, _MAX_TITLE)
        moved = url != tab["url"]
        if moved:
            tab["url"], tab["title"] = url, title
        retitled = bool(title) and title != tab["title"]
        if retitled:
            tab["title"] = title
        if moved or retitled:
            self.dirty = True
        return moved, retitled and not moved


class LinkList:
    """Pages by address, newest first: the history (``put`` moves a page to the top) and the bookmarks."""

    def __init__(self, items=None, limit=MAX_HISTORY):
        self.limit = limit
        self.items = []
        self.dirty = False
        seen = set()
        for it in items or []:
            if not isinstance(it, dict):
                continue
            url = _clip(it.get("url"), _MAX_URL)
            if is_web(url) and url not in seen:
                seen.add(url)
                self.items.append({"url": url, "title": _clip(it.get("title"), _MAX_TITLE), "ts": _num(it.get("ts"))})
        del self.items[limit:]

    @classmethod
    def from_data(cls, data, limit=MAX_HISTORY):
        return cls(data if isinstance(data, list) else [], limit)

    def to_data(self):
        return [dict(i) for i in self.items]

    def _index(self, url):
        return next((n for n, i in enumerate(self.items) if i["url"] == url), -1)

    def get(self, url):
        i = self._index(_clip(url, _MAX_URL))
        return self.items[i] if i >= 0 else None

    def has(self, url):
        return self.get(url) is not None

    def put(self, url, title="", bump=True):
        """Adds a page (True) or updates the one already there (False). ``bump``: move it to the top."""
        url, title = _clip(url, _MAX_URL), _clip(title, _MAX_TITLE)
        if not is_web(url):
            return False
        i = self._index(url)
        self.dirty = True
        if i >= 0:
            item = self.items[i]
            if title:
                item["title"] = title
            if bump:
                item["ts"] = time.time()
                self.items.insert(0, self.items.pop(i))
            return False
        self.items.insert(0, {"url": url, "title": title, "ts": time.time()})
        del self.items[self.limit:]
        return True

    def retitle(self, url, title):
        """A new title for a page already in the list (the page finished loading / a rename)."""
        item, title = self.get(url), _clip(title, _MAX_TITLE)
        if item is None or not title or item["title"] == title:
            return False
        item["title"] = title
        self.dirty = True
        return True

    def remove(self, url):
        i = self._index(_clip(url, _MAX_URL))
        if i < 0:
            return False
        self.items.pop(i)
        self.dirty = True
        return True

    def clear(self):
        if self.items:
            self.items = []
            self.dirty = True

    def search(self, text):
        """Every word typed must be in the title or the address (any case)."""
        words = str(text or "").lower().split()
        if not words:
            return list(self.items)
        return [i for i in self.items if all(w in (i["title"] + " " + i["url"]).lower() for w in words)]
