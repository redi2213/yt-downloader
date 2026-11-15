"""In-app browser page tools (plain Python, no Kivy needed):
    python3 tests/browser_tools_test.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import browser_tabs as bt, browser_tools as tools  # noqa: E402

# -- translate: address out and back
u = "https://www.example.com/a/b?x=1&y=2#top"
t = tools.translate_url(u)
assert t.startswith("https://www-example-com.translate.goog/a/b?x=1&y=2&_x_tr_sl=auto&_x_tr_tl=fa") and t.endswith("#top")
assert tools.is_translated(t) and not tools.is_translated(u)
assert tools.original_url(t) == "https://www.example.com/a/b?x=1&y=2#top"
assert tools.translate_url(t) == t                  # an already translated page stays the same
for host in ("a-b.example.com", "xn--p1ai.test", "my-site.co.uk", "plain.org"):
    link = f"https://{host}/p?q=1"
    assert tools.original_url(tools.translate_url(link)) == link, host
assert tools.translate_url("about:blank") == "" and tools.translate_url("https://a.test:8443/x") == ""
assert tools.translate_url("") == "" and tools.original_url("") == ""
assert tools.host_of("https://Sub.Site.test/x") == "sub.site.test" and tools.host_of("junk") == ""

# -- desktop view is kept with its tab
ts = bt.Tabs()
tab = ts.current()
assert not ts.is_desktop(tab["id"]) and "desktop" not in tab
ts.dirty = False
assert ts.set_desktop(tab["id"], True) and ts.is_desktop(tab["id"]) and ts.dirty
assert bt.Tabs.from_data(ts.to_data()).is_desktop(tab["id"])
ts.dirty = False
assert ts.set_desktop(tab["id"], True) and not ts.dirty           # no change: nothing to save
assert ts.set_desktop(tab["id"], False) and "desktop" not in ts.current() and ts.dirty
assert ts.set_desktop("nope", True) is False
print("browser tools tests: ok")
