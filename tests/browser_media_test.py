"""In-app browser list logic: dedupe, sorting, selection totals (plain Python, no Kivy needed):
    python3 tests/browser_media_test.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import browser_media as bm  # noqa: E402


def rec(url, referer="https://site.test/p1"):
    return {"url": url, "src": "net", "referer": referer, "ua": "", "cookie": ""}


s = bm.Session()
s.merge({"epoch": 1, "page": "https://site.test/p1", "title": "T", "items": [
    rec("https://www.cdn.test/a/Video_720p.mp4?token=1"),
    rec("https://cdn.test/a/Video_720p.mp4?token=2"),      # same file, other token / www: one row
    rec("https://cdn.test/b/song.mp3"),
    rec("https://cdn.test/c/live.m3u8"),
]})
assert s.count() == 3, s.count()

# a new page keeps what was found; Clear empties it
s.merge({"epoch": 2, "page": "https://site.test/p2", "title": "T2", "items": [rec("https://cdn.test/d/zzz.webm", "https://site.test/p2")]})
assert s.count() == 4
assert [e["name"] for e in bm.sort_entries(s.all_entries(), "newest")][0] == "zzz.webm"
assert [e["name"] for e in bm.sort_entries(s.all_entries(), "oldest")][0].lower() == "video_720p.mp4"

# sizes: biggest first, unknown last; selection totals
for e in s.items.values():
    e["size"] = {"song.mp3": 3 * 1024 ** 2, "zzz.webm": 50 * 1024 ** 2}.get(e["name"])
by_size = [e["name"] for e in bm.sort_entries(s.all_entries(), "size")]
assert by_size[:2] == ["zzz.webm", "song.mp3"], by_size
s.selected = {e["key"] for e in s.all_entries() if e["name"] in ("zzz.webm", "song.mp3", "live.m3u8") or e["kind"] == "hls"}
count, total, unknown = bm.selection_summary(s.all_entries(), s.selected)
assert (count, total, unknown) == (3, 53 * 1024 ** 2, 1), (count, total, unknown)

# quality / name / type
assert bm.quality_height({"quality": "1080p60"}) == 1080 and bm.quality_height({"kind": "audio"}) == 0
assert bm.quality_height({"quality": ""}) == -1
names = [{"key": str(i), "name": n, "kind": "video", "quality": q, "ext": ".mp4"}
         for i, (n, q) in enumerate([("e10", "480p"), ("e2", "1080p"), ("e1", "")])]
assert [e["name"] for e in bm.sort_entries(names, "name")] == ["e1", "e2", "e10"]
assert [e["name"] for e in bm.sort_entries(names, "quality")] == ["e2", "e10", "e1"]
assert bm.sort_entries(names, "type") and bm.sort_entries(names, "nonsense")

# HLS master: the qualities are rows; the same playlist seen alone is not a second row
m = bm.Session()
m.merge({"epoch": 1, "page": "https://h.test/", "items": [rec("https://h.test/master.m3u8"), rec("https://h.test/v720.m3u8")]})
m.items[bm.dedupe_key("https://h.test/master.m3u8")]["variants"] = [
    {"url": "https://h.test/v720.m3u8", "height": 720, "bandwidth": 1, "label": "720p"}]
rows = m.all_entries()
assert len(rows) == 1 and rows[0]["quality"] == "720p", rows

# yt-dlp rows: size parsed, kept per page, Clear does not re-read by itself
y = bm.Session()
y.merge({"epoch": 1, "page": "https://youtu.be/abcdefghijk", "title": "V", "items": []})
y.set_ytdlp([("f1", "720p", "120 MB", "avc1"), ("f2", "1080p", "1.50 GB", "vp9")])
assert [e["size"] for e in y.all_entries()[:2]] == [int(1.5 * 1024 ** 3), 120 * 1024 ** 2]
y.clear()
assert y.all_entries() == [] and y.ytdlp_for == y.page
y.restart_scan()
assert y.ytdlp_for is None
print("browser_media_test: ok")
