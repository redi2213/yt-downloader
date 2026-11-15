"""Background work of the in-app browser: file sizes and types (from the server's headers), HLS qualities and the
yt-dlp quality list; also the saved file-type rules."""
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from api import browser_prefs
from core import browser_media as bm, browser_tabs as bt, segmented_download
from core.async_utils import run_in_background
from services import phone_youtube_service


PROBE_BATCH = 24      # links looked at in one go: a page with hundreds of links does not flood the phone


def default_sort():
    value = browser_prefs.get_sort()
    return value if value in bm.SORT_MODES else "newest"


def save_default_sort(mode):
    try:
        browser_prefs.set_sort(mode)
    except Exception:
        pass


def load_rules():
    """The file-type rules saved on this phone (all types on when nothing was saved yet)."""
    try:
        raw = browser_prefs.get_types()
        custom = [c for c in browser_prefs.get_custom().split(",") if c]
    except Exception:
        raw, custom = "", []
    if not raw:
        enabled = set(bm.CATEGORIES)
    elif raw == "none":
        enabled = set()
    else:
        enabled = {c for c in raw.split(",") if c in bm.CATEGORIES}
    return bm.Rules(enabled, custom)


def save_rules(rules):
    try:
        browser_prefs.set_types(",".join(c for c in bm.CATEGORIES if c in rules.enabled) or "none")
        browser_prefs.set_custom(",".join(e.lstrip(".") for e in rules.custom))
    except Exception:
        pass


def start_probe(session, on_update=None):
    """Looks up the size of the next files (and the qualities of HLS master playlists) not looked at yet."""
    if session.probing:
        return
    todo = [item for item in session.items.values() if not item.get("probed")][:PROBE_BATCH]
    if not todo:
        return
    session.probing = True
    run_in_background(_probe_all, session, todo, on_update)


def _probe_all(session, items, on_update):
    def work(item):
        _probe_one(item, session.rules)
        session.touch()

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(work, items))
    finally:
        session.probing = False
        session.touch()
    if on_update:
        on_update()


def fetch_headers(url, headers=None):
    """What the server says about a file: {mime, disp, length} (HEAD; a one-byte GET when HEAD says nothing)."""
    h = dict(headers or {})
    try:
        r = requests.head(url, headers=h, allow_redirects=True, timeout=10)
        if r.status_code < 400 and (r.headers.get("Content-Type") or r.headers.get("Content-Length")):
            return {"mime": r.headers.get("Content-Type", ""), "disp": r.headers.get("Content-Disposition", ""),
                    "length": r.headers.get("Content-Length")}
    except Exception:
        pass
    h["Range"] = "bytes=0-0"
    r = requests.get(url, headers=h, allow_redirects=True, timeout=10, stream=True)
    try:
        total = r.headers.get("Content-Length")
        whole = (r.headers.get("Content-Range") or "").rpartition("/")[2]
        if whole.isdigit():
            total = whole          # "bytes 0-0/12345": the whole file, not the one byte
        return {"mime": r.headers.get("Content-Type", ""), "disp": r.headers.get("Content-Disposition", ""),
                "length": total}
    finally:
        r.close()


def _probe_one(item, rules=None):
    headers = item.get("headers") or None
    try:
        if item["kind"] in ("video", "audio"):
            total, _ranges = segmented_download.probe(item["url"], headers)
            item["size"] = total or None
        elif item["kind"] == "hls":
            r = requests.get(item["url"], headers=headers, timeout=10)
            r.raise_for_status()
            item["variants"] = bm.parse_m3u8_variants(r.text, item["url"]) or None
        else:       # archive, APK, package, document, custom, unknown: name, type and size come from the headers
            bm.apply_headers(item, fetch_headers(item["url"], headers), rules or bm.Rules())
    except Exception:
        pass     # the size stays unknown: the file can still be downloaded
    finally:
        item["probed"] = True


def start_ytdlp(page_url, on_done):
    """yt-dlp on the phone lists the qualities of a supported page. ``on_done({"ok", "formats" | "error"})``."""
    def work():
        try:
            on_done({"ok": True, "formats": phone_youtube_service.list_qualities(page_url)})
        except Exception as e:
            on_done({"ok": False, "error": str(e)[:80]})
    run_in_background(work)


# -- tabs, history and bookmarks (they stay after the app is closed) -----------------------------------------------
class BrowserState:
    """The open tabs, the history and the bookmarks. Changes are written at most every few seconds
    (``save_if_due``, called by the browser screen's timer) and at once on ``flush`` (after a user action)."""

    def __init__(self):
        self.tabs = bt.Tabs.from_data(_read("tabs"))
        self.history = bt.LinkList.from_data(_read("history"), bt.MAX_HISTORY)
        self.bookmarks = bt.LinkList.from_data(_read("bookmarks"), bt.MAX_BOOKMARKS)
        self._last = 0.0

    def _parts(self):
        return (("tabs", self.tabs), ("history", self.history), ("bookmarks", self.bookmarks))

    def page_seen(self, tab_id, url, title):
        """The page of a tab reported its address / title: the tab and the history follow."""
        moved, retitled = self.tabs.update(tab_id, url, title)
        if moved:
            self.history.put(url, title)
        elif retitled:
            self.history.retitle(url, title)

    def save_if_due(self, gap=2.0):
        if time.time() - self._last >= gap and any(obj.dirty for _name, obj in self._parts()):
            self.flush()

    def flush(self):
        for name, obj in self._parts():
            if not obj.dirty:
                continue
            try:
                browser_prefs.set_data(name, obj.to_data())
                obj.dirty = False
            except Exception:
                pass            # the next change tries again
        self._last = time.time()


def _read(name):
    try:
        return browser_prefs.get_data(name)
    except Exception:
        return None


_state = None


def state():
    """The one BrowserState of the app (read from the phone the first time it is asked for)."""
    global _state
    if _state is None:
        _state = BrowserState()
    return _state
