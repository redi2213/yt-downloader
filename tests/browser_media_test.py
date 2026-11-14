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

# quality groups: only a certain relation groups rows
g = bm.Session()
g.merge({"epoch": 1, "page": "https://site.test/p1", "title": "T", "items": [
    rec("https://cdn.test/a/Movie_360p.mp4"), rec("https://cdn.test/a/Movie_720p.mp4"),   # one video, two qualities
    rec("https://cdn.test/a/Other_720p.mp4"),                                              # alone: not a group
    rec("https://cdn.test/b/clip_480.mp4"), rec("https://cdn.test/b/clip_1080.mp4"),      # _480 / _1080 suffix
    rec("https://cdn.test/c/x.mp4"), rec("https://cdn.test/d/x.mp4"),                      # same name, other folders
]})
units = bm.group_units(g.all_entries())
grouped = {u["name"]: [m["quality"] for m in u["members"]] for u in units if u["members"]}
assert set(grouped) == {"Movie.mp4", "clip.mp4"}, grouped
assert sum(1 for u in units if u["members"] is None) == 3          # Other_720p, x.mp4, x.mp4
assert bm.group_base("https://cdn.test/c/x.mp4") == "" and bm.strip_quality("Movie_720p.mp4") == "Movie.mp4"
assert bm.strip_quality("clip_1080.mp4") == "clip.mp4" and bm.strip_quality("720p.mp4") == "720p.mp4"
for mode in bm.SORT_MODES:
    out = bm.sort_units(units, mode)
    assert len(out) == len(units) and {u["key"] for u in out} == {u["key"] for u in units}, mode
    for u in out:
        if u["members"] and mode != "size":          # inside a group: best quality first
            q = [m["quality"] for m in u["members"]]
            assert q in (["720p", "360p"], ["1080p", "480p"]), (mode, q)
assert bm.sort_units(units, "name")[0]["name"] == "clip.mp4"
assert bm.sort_units(units, "newest")[0]["key"] != bm.sort_units(units, "oldest")[0]["key"]

# the same on a yt-dlp page and on an HLS master; Clear closes the groups
y2 = bm.Session()
y2.merge({"epoch": 1, "page": "https://youtu.be/abcdefghijk", "title": "V", "items": []})
y2.set_ytdlp([("f1", "720p", "120 MB", "avc1"), ("f2", "1080p", "1.50 GB", "vp9")])
yu = bm.group_units(y2.all_entries())
assert len(yu) == 1 and len(yu[0]["members"]) == 3 and yu[0]["name"] == "V", yu
assert bm.sort_units(yu, "size")[0]["members"][0]["size"] == int(1.5 * 1024 ** 3)
y2.open_groups.add(yu[0]["key"])
y2.clear()
assert not y2.open_groups
m2 = bm.Session()
m2.merge({"epoch": 1, "page": "https://h.test/", "items": [rec("https://h.test/master.m3u8")]})
m2.items[bm.dedupe_key("https://h.test/master.m3u8")]["variants"] = [
    {"url": "https://h.test/v720.m3u8", "height": 720, "bandwidth": 1, "label": "720p"},
    {"url": "https://h.test/v480.m3u8", "height": 480, "bandwidth": 1, "label": "480p"}]
hu = bm.group_units(m2.all_entries())
assert len(hu) == 1 and len(hu[0]["members"]) == 2, hu
print("browser_media_test: ok")
