"""In-app browser tabs, history and bookmarks (plain Python, no Kivy needed):
    python3 tests/browser_tabs_test.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import browser_media as bm, browser_tabs as bt  # noqa: E402

# -- tabs
ts = bt.Tabs()
first = ts.current()
assert ts.count() == 1 and first["url"] == ""
t2 = ts.new("https://a.test/")
assert ts.active == t2["id"] and t2["url"] == "https://a.test/" and ts.count() == 2
t3 = ts.new()
assert ts.count() == 3 and ts.active == t3["id"]

# every tab has its own found files
s2 = ts.session_for(t2["id"])
s3 = ts.session_for(t3["id"])
assert s2 is not s3 and ts.session_for(t2["id"]) is s2
s2.merge({"epoch": 1, "page": "https://a.test/", "title": "A", "items": [
    {"url": "https://cdn.test/a.mp4", "src": "net", "referer": "https://a.test/"}]})
assert s2.count() == 1 and s3.count() == 0

# page reports: address / title follow the tab; about:blank and junk are ignored
assert ts.update(t3["id"], "about:blank", "x") == (False, False)
assert ts.update(t3["id"], "https://b.test/x", "") == (True, False)
assert ts.update(t3["id"], "https://b.test/x", "B page") == (False, True)
assert ts.update(t3["id"], "https://b.test/x", "B page") == (False, False)
assert ts.find(t3["id"])["title"] == "B page"

# closing: the neighbour becomes active; the last tab never leaves the browser empty
assert ts.close(t3["id"])["id"] == t2["id"] and ts.count() == 2
assert ts.close("nope")["id"] == ts.active
ts.close(first["id"])
last = ts.close(ts.active)
assert ts.count() == 1 and last["url"] == "" and ts.active == last["id"]
ts.new("https://c.test/")
ts.close_all()
assert ts.count() == 1 and ts.current()["url"] == ""

# limit
big = bt.Tabs()
for _ in range(bt.MAX_TABS + 5):
    big.new("https://x.test/")
assert big.count() == bt.MAX_TABS and big.new() is None

# a tab left in the background keeps only its newest files
sess = bm.Session()
sess.merge({"epoch": 1, "page": "https://a.test/", "title": "", "items": [
    {"url": f"https://cdn.test/f{n}.mp4", "src": "net", "referer": "https://a.test/"} for n in range(50)]})
sess.trim(10)
assert len(sess.items) == 10 and "f49" in " ".join(i["url"] for i in sess.items.values())

# saved and read back (junk is dropped)
back = bt.Tabs.from_data(big.to_data())
assert back.count() == big.count() and back.active == big.active
assert bt.Tabs.from_data("junk").count() == 1 and bt.Tabs.from_data({"tabs": [{"id": "a", "url": "ftp://x"}, 5]}).count() == 1
assert bt.Tabs.from_data({"tabs": [{"id": "a"}, {"id": "a"}], "active": "zz"}).count() == 1

# -- history / bookmarks
h = bt.LinkList(limit=3)
assert h.put("https://a.test/", "A") is True
assert h.put("https://b.test/", "B") is True
assert h.put("https://a.test/", "A2") is False            # again: moved to the top, title updated
assert [i["url"] for i in h.items] == ["https://a.test/", "https://b.test/"] and h.items[0]["title"] == "A2"
assert h.put("ftp://x.test/") is False and h.put("about:blank") is False and len(h.items) == 2
h.put("https://c.test/")
h.put("https://d.test/")
assert len(h.items) == 3 and not h.has("https://b.test/")      # the oldest goes at the limit
assert h.retitle("https://d.test/", "D") and not h.retitle("https://d.test/", "D")
assert [i["url"] for i in h.search("  D ")] == ["https://d.test/"]
assert h.search("zzz") == [] and len(h.search("")) == 3
assert h.remove("https://d.test/") and not h.remove("https://d.test/")
h.dirty = False
h.clear()
assert h.items == [] and h.dirty

b = bt.LinkList(limit=bt.MAX_BOOKMARKS)
assert b.put("https://a.test/", "A", bump=False) is True
assert b.put("https://z.test/", "Z", bump=False) is True
assert b.put("https://a.test/", "", bump=False) is False
assert [i["url"] for i in b.items] == ["https://z.test/", "https://a.test/"] and b.get("https://a.test/")["title"] == "A"
assert bt.LinkList.from_data(b.to_data()).items == b.items
assert bt.LinkList.from_data({"x": 1}).items == [] and bt.LinkList.from_data([1, {"url": "x"}, {"url": "https://q.test"}]).items[0]["url"] == "https://q.test"

# -- display helpers
assert bt.short_url("https://www.site.test/a/b/") == "site.test/a/b"
assert len(bt.short_url("https://site.test/" + "x" * 200)) == 70
assert bt.when(0, now=0) != "" and bt.when("bad") == ""
print("browser tabs tests: ok")
