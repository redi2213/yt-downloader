"""Background work of the in-app browser: file sizes, HLS qualities and the yt-dlp quality list."""
from concurrent.futures import ThreadPoolExecutor

import requests

from api import browser_prefs
from core import browser_media as bm, segmented_download
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
        _probe_one(item)
        session.touch()

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(work, items))
    finally:
        session.probing = False
        session.touch()
    if on_update:
        on_update()


def _probe_one(item):
    headers = item.get("headers") or None
    try:
        if item["kind"] in ("video", "audio"):
            total, _ranges = segmented_download.probe(item["url"], headers)
            item["size"] = total or None
        elif item["kind"] == "hls":
            r = requests.get(item["url"], headers=headers, timeout=10)
            r.raise_for_status()
            item["variants"] = bm.parse_m3u8_variants(r.text, item["url"]) or None
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
