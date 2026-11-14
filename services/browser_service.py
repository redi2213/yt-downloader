"""Background work of the in-app browser: file sizes, HLS qualities and the yt-dlp quality list."""
from concurrent.futures import ThreadPoolExecutor

import requests

from core import browser_media as bm, segmented_download
from core.async_utils import run_in_background
from services import phone_youtube_service


def start_probe(session, on_update=None):
    """Looks up the size of every file (and the qualities of every HLS master playlist) not looked at yet."""
    todo = [item for item in session.items.values() if not item.get("probed")]
    if not todo:
        return
    for item in todo:
        item["probed"] = True
    run_in_background(_probe_all, todo, on_update)


def _probe_all(items, on_update):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_probe_one, items))
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


def start_ytdlp(page_url, on_done):
    """yt-dlp on the phone lists the qualities of a supported page. ``on_done({"ok", "formats" | "error"})``."""
    def work():
        try:
            on_done({"ok": True, "formats": phone_youtube_service.list_qualities(page_url)})
        except Exception as e:
            on_done({"ok": False, "error": str(e)[:80]})
    run_in_background(work)
